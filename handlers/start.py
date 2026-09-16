"""Регистрация пользователя и открытие главного экрана."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import KICKED, MEMBER, ChatMemberUpdatedFilter, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import ChatMemberUpdated, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _
from sqlalchemy.ext.asyncio import AsyncSession

from common import keyboard
from common.locale import normalize_locale
from common.screen import show_command_screen
from database.orm_users import (
    orm_get_user,
    orm_register_user,
    orm_update_status,
)

logger = logging.getLogger(__name__)
start_router = Router()
start_router.message.filter(F.chat.type == "private")


def main_screen(
    current_question: int,
    result: int | None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Сформировать главный экран для текущего этапа теста."""
    if current_question == 1:
        return (
            _(
                "Factuality Test.\n"
                "Тест по книге Ханса Рослинга «Фактологичность»\n\n"
                "Готовы пройти тест?"
            ),
            keyboard.inline_start_test(),
        )
    if current_question > 13:
        return (
            _(
                "Factuality Test.\n"
                "Тест по книге Ханса Рослинга «Фактологичность»\n\n"
                "Вы прошли тест!\n\n"
                "Ваш результат: {correct_count}/13\n"
            ).format(correct_count=result),
            keyboard.get_callback_btns(
                btns={
                    _("Правильные ответы"): "correct_answers",
                    _("О книге"): "about_book",
                    _("О тесте"): "about_test",
                },
                sizes=(1, 1, 1),
            ),
        )
    return (
        _(
            "Factuality Test.\n"
            "Тест по книге Ханса Рослинга «Фактологичность»\n\n"
            "Вы остановились на {current_question} вопросе.\n"
            "Желаете продолжить тест?"
        ).format(current_question=current_question),
        keyboard.inline_continue_test(),
    )


@start_router.message(CommandStart())
async def start_cmd(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext,
) -> None:
    """Зарегистрировать пользователя и показать главный экран."""
    user = message.from_user
    user_data = {
        "user_id": user.id,
        "user_name": user.username or "None",
        "full_name": user.full_name or "None",
        "locale": normalize_locale(user.language_code),
        "status": "member",
        "flag": 1,
    }

    try:
        registration = await orm_register_user(session, user_data)
        current_question = registration.current_question
        result = registration.result
        text, reply_markup = main_screen(current_question, result)
        await state.update_data(
            current_question=current_question,
            result=result,
        )
        await show_command_screen(message, state, text, reply_markup)

        if registration.is_new:
            safe_name = escape(user.username or user.full_name or "None")
            await bot.send_message(
                chat_id=bot.home_group[0],
                text=f"✅ @{safe_name} - подписался на бота",
            )

    except Exception:
        await session.rollback()
        logger.exception("Ошибка обработки /start пользователя %s", user.id)


@start_router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=KICKED)
)
async def process_user_blocked_bot(
    event: ChatMemberUpdated,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Зафиксировать блокировку бота пользователем."""
    user_id = event.from_user.id
    safe_name = escape(event.from_user.username or event.from_user.full_name)
    await orm_update_status(session, user_id, "kicked")
    await bot.send_message(
        chat_id=bot.home_group[0],
        text=f"⛔️ @{safe_name} - заблокировал бота",
    )


@start_router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=MEMBER)
)
async def process_user_unblocked_bot(
    event: ChatMemberUpdated,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Зафиксировать разблокировку бота пользователем."""
    user_id = event.from_user.id
    if await orm_get_user(session, user_id) is None:
        return

    full_name = event.from_user.full_name or ""
    safe_name = escape(event.from_user.username or full_name)
    await orm_update_status(session, user_id, "member")
    await bot.send_message(
        chat_id=user_id,
        text=_("{full_name}, Добро пожаловать обратно!").format(
            full_name=escape(full_name)
        ),
    )
    await bot.send_message(
        chat_id=bot.home_group[0],
        text=f"♻️ @{safe_name} - разблокировал бота",
    )
