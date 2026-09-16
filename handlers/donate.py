"""Приём и возврат донатов Telegram Stars."""

from __future__ import annotations

import asyncio
import logging
import secrets
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    TransactionPartnerUser,
)
from aiogram.utils.i18n import gettext as _
from aiogram.utils.keyboard import InlineKeyboardBuilder
from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common import keyboard
from common.screen import show_command_screen
from database.orm_payments import (
    orm_get_payment,
    orm_mark_payment_refunded,
    orm_record_payment,
)

logger = logging.getLogger(__name__)

donate_router = Router()
donate_router.message.filter(F.chat.type == "private")

ALLOWED_DONATION_AMOUNTS = {10, 50, 100, 500}
PAYMENT_RECONCILIATION_LIMIT = 1_000
PAYMENT_RECONCILIATION_TIMEOUT = 10
REFUND_LOOKUP_COOLDOWN_SECONDS = 30
refund_lookup_cooldown: TTLCache[int, bool] = TTLCache(
    maxsize=10_000,
    ttl=REFUND_LOOKUP_COOLDOWN_SECONDS,
)
refund_lookup_semaphore = asyncio.Semaphore(2)


async def show_refund_status(
    message: Message,
    state: FSMContext,
    text: str,
) -> None:
    """Показать результат возврата в рабочем сообщении."""
    await show_command_screen(
        message=message,
        state=state,
        text=text,
        reply_markup=keyboard.get_callback_btns(
            btns={_("↩️ Назад"): "back_to_main"},
            sizes=(1,),
        ),
    )


class Donate(StatesGroup):
    """Состояния оформления доната."""

    donate_input = State()
    donate_send = State()


@donate_router.callback_query(F.data == "donate")
async def cmd_donate(callback: CallbackQuery, state: FSMContext) -> None:
    """Показать варианты суммы доната."""
    await callback.answer()
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10 ⭐️", callback_data="donate_10"),
                InlineKeyboardButton(text="50 ⭐️", callback_data="donate_50"),
            ],
            [
                InlineKeyboardButton(text="100 ⭐️", callback_data="donate_100"),
                InlineKeyboardButton(text="500 ⭐️", callback_data="donate_500"),
            ],
            [
                InlineKeyboardButton(
                    text=_("↩️ Назад"), callback_data="back_to_main"
                )
            ],
        ]
    )
    new_message = await callback.message.edit_text(
        text=_("Поддержать проект донатом"),
        reply_markup=buttons,
    )
    await state.update_data(last_message_id=new_message.message_id)
    await state.set_state(Donate.donate_input)


@donate_router.callback_query(
    Donate.donate_input,
    F.data.startswith("donate_"),
)
async def cmd_donate_input(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """Создать счёт на выбранную сумму."""
    try:
        amount = int((callback.data or "").rsplit("_", maxsplit=1)[-1])
    except ValueError:
        await callback.answer(_("Некорректная сумма."), show_alert=True)
        return

    if amount not in ALLOWED_DONATION_AMOUNTS:
        await callback.answer(_("Некорректная сумма."), show_alert=True)
        return

    await callback.answer()
    payload = (
        f"donation:{callback.from_user.id}:"
        f"{secrets.token_urlsafe(18)}"
    )
    invoice_keyboard = InlineKeyboardBuilder()
    invoice_keyboard.button(
        text=_("{amount} XTR").format(amount=amount),
        pay=True,
    )
    invoice_keyboard.button(
        text=_("↩️ Назад"),
        callback_data="donate_back_to_main",
    )
    invoice_keyboard.adjust(1)

    new_message = await callback.message.answer_invoice(
        title=_("Поддержать проект донатом"),
        description=_("На сумму"),
        prices=[LabeledPrice(label="XTR", amount=amount)],
        provider_token="",
        payload=payload,
        currency="XTR",
        reply_markup=invoice_keyboard.as_markup(),
    )
    try:
        await callback.message.delete()
    except TelegramAPIError:
        logger.info("Не удалось удалить экран перед счётом")

    await state.update_data(
        donate_amount=amount,
        invoice_payload=payload,
        last_message_id=new_message.message_id,
    )
    await state.set_state(Donate.donate_send)


@donate_router.pre_checkout_query()
async def pre_checkout_query(query: PreCheckoutQuery) -> None:
    """Проверить параметры счёта перед оплатой."""
    expected_prefix = f"donation:{query.from_user.id}:"
    valid = (
        query.currency == "XTR"
        and query.total_amount in ALLOWED_DONATION_AMOUNTS
        and query.invoice_payload.startswith(expected_prefix)
    )
    if valid:
        await query.answer(ok=True)
        return
    await query.answer(
        ok=False,
        error_message=_("Параметры платежа устарели. Создайте новый счёт."),
    )


@donate_router.message(F.successful_payment)
async def on_successful_payment(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Надёжно зарегистрировать успешный платёж."""
    payment = message.successful_payment
    if payment is None:
        return

    charge_id = payment.telegram_payment_charge_id
    was_recorded = await orm_record_payment(
        session=session,
        charge_id=charge_id,
        user_id=message.from_user.id,
        invoice_payload=payment.invoice_payload,
        currency=payment.currency,
        total_amount=payment.total_amount,
        paid_at=message.date,
    )

    data = await state.get_data()
    if (
        not was_recorded
        and data.get("last_payment_charge_id") == charge_id
    ):
        logger.info("Повторное уведомление о платеже %s пропущено", charge_id)
        return

    last_message_id = data.get("last_message_id")
    if last_message_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=last_message_id,
            )
        except TelegramAPIError:
            logger.info("Не удалось удалить оплаченный счёт %s", charge_id)

    new_message = await message.answer(
        text=_(
            "<b>Спасибо!</b>\nВаш донат успешно принят.\n\n"
            "ID транзакции:\n<code>{t_id}</code>"
        ).format(t_id=escape(charge_id)),
        message_effect_id="5159385139981059251",
        reply_markup=keyboard.get_callback_btns(
            btns={_("↩️ Назад"): "back_to_main"},
            sizes=(1,),
        ),
    )
    await state.set_state(None)
    await state.update_data(
        last_message_id=new_message.message_id,
        donate_amount=None,
        invoice_payload=None,
        last_payment_charge_id=charge_id,
    )
async def reconcile_recent_payments(
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> int:
    """Восстановить пропущенные входящие платежи из Telegram."""
    transactions = await bot.get_star_transactions(limit=100)
    restored = 0
    async with session_pool() as session:
        for transaction in transactions.transactions:
            source = transaction.source
            if not isinstance(source, TransactionPartnerUser):
                continue
            if source.transaction_type != "invoice_payment":
                continue
            was_added = await orm_record_payment(
                session=session,
                charge_id=transaction.id,
                user_id=source.user.id,
                invoice_payload=source.invoice_payload or "reconciled",
                currency="XTR",
                total_amount=transaction.amount,
                paid_at=transaction.date,
            )
            restored += int(was_added)
    return restored


async def reconcile_payment_by_charge(
    bot: Bot,
    session: AsyncSession,
    charge_id: str,
    user_id: int,
) -> bool:
    """Найти старый платёж Telegram и перенести его в постоянный учёт."""
    page_size = 100
    async with asyncio.timeout(PAYMENT_RECONCILIATION_TIMEOUT):
        for offset in range(0, PAYMENT_RECONCILIATION_LIMIT, page_size):
            page = await bot.get_star_transactions(
                offset=offset,
                limit=page_size,
            )
            for transaction in page.transactions:
                if transaction.id != charge_id:
                    continue

                source = transaction.source
                if not isinstance(source, TransactionPartnerUser):
                    return False
                if source.transaction_type != "invoice_payment":
                    return False
                if source.user.id != user_id:
                    return False

                await orm_record_payment(
                    session=session,
                    charge_id=transaction.id,
                    user_id=source.user.id,
                    invoice_payload=source.invoice_payload or "reconciled",
                    currency="XTR",
                    total_amount=transaction.amount,
                    paid_at=transaction.date,
                )
                return True

            if len(page.transactions) < page_size:
                break
    return False


@donate_router.message(Command("refundd"))
async def command_refund_handler(
    message: Message,
    bot: Bot,
    command: CommandObject,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Вернуть принадлежащий пользователю учтённый донат."""
    charge_id = (command.args or "").strip()
    if not charge_id:
        await show_refund_status(
            message,
            state,
            _("Укажите ID транзакции после команды /refundd."),
        )
        return

    if len(charge_id) > 255 or any(char.isspace() for char in charge_id):
        await show_refund_status(
            message,
            state,
            _("Транзакция не найдена."),
        )
        return

    payment = await orm_get_payment(session, charge_id, message.from_user.id)
    if payment is None:
        user_id = message.from_user.id
        if user_id in refund_lookup_cooldown:
            was_found = False
        else:
            refund_lookup_cooldown[user_id] = True
            try:
                async with refund_lookup_semaphore:
                    was_found = await reconcile_payment_by_charge(
                        bot=bot,
                        session=session,
                        charge_id=charge_id,
                        user_id=user_id,
                    )
            except Exception:
                logger.exception(
                    "Не удалось найти старый платёж %r",
                    charge_id,
                )
                was_found = False
        if was_found:
            payment = await orm_get_payment(
                session,
                charge_id,
                message.from_user.id,
            )

    if payment is None:
        await show_refund_status(
            message,
            state,
            _("Транзакция не найдена."),
        )
        return
    if payment.status == "refunded":
        await show_refund_status(
            message,
            state,
            _("Этот донат уже возвращён."),
        )
        return

    try:
        await bot.refund_star_payment(
            user_id=message.from_user.id,
            telegram_payment_charge_id=charge_id,
        )
    except TelegramBadRequest as error:
        error_text = error.message.upper()
        if "ALREADY" in error_text and "REFUND" in error_text:
            await orm_mark_payment_refunded(session, charge_id)
            await show_refund_status(
                message,
                state,
                _("Этот донат уже возвращён."),
            )
            return
        logger.warning("Telegram отклонил возврат %s: %s", charge_id, error)
        await show_refund_status(
            message,
            state,
            _("Не удалось вернуть донат. Попробуйте позже."),
        )
        return
    except TelegramAPIError:
        logger.exception("Сбой Telegram при возврате %s", charge_id)
        await show_refund_status(
            message,
            state,
            _("Не удалось вернуть донат. Попробуйте позже."),
        )
        return

    await orm_mark_payment_refunded(session, charge_id)
    await show_refund_status(
        message,
        state,
        _("Донат успешно возвращён."),
    )
