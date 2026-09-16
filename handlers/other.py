"""Настройки, справка и обработка прочих сообщений."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommandScopeChat,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.i18n import I18n
from aiogram.utils.i18n import gettext as _
from sqlalchemy.ext.asyncio import AsyncSession

from common import keyboard
from common.comands import PRIVATE_COMMANDS
from common.locale import normalize_locale
from common.screen import show_command_screen
from database.orm_answers import orm_get_current_question
from database.orm_users import orm_update_locale

logger = logging.getLogger(__name__)
other_router = Router()
other_router.message.filter(F.chat.type == "private")


def keyboard_language() -> InlineKeyboardMarkup:
    """Создать клавиатуру выбора языка."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_("🇬🇧 Английский"), callback_data="locale_en"
                ),
                InlineKeyboardButton(
                    text=_("🇷🇺 Русский"), callback_data="locale_ru"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_("🇪🇸 Испанский"), callback_data="locale_es"
                ),
                InlineKeyboardButton(
                    text=_("🇺🇦 Украинский"), callback_data="locale_uk"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_("↩️ Назад"), callback_data="back_to_main"
                )
            ],
        ]
    )


def language_screen(locale: str) -> tuple[str, InlineKeyboardMarkup]:
    """Сформировать экран выбора языка."""
    language_labels = {
        "en": _("English 🇬🇧"),
        "es": _("Español 🇪🇸"),
        "ru": _("Русский 🇷🇺"),
        "uk": _("Українська 🇺🇦"),
    }
    text = _(
        "Настройки языка\n"
        "Текущий язык: {language}\n\n"
        "Выберите язык, на котором будет работать бот"
    ).format(language=language_labels[normalize_locale(locale)])
    return text, keyboard_language()


@other_router.message(Command("language"))
async def language_cmd(
    message: Message,
    state: FSMContext,
) -> None:
    """Показать настройки языка в рабочем сообщении."""
    data = await state.get_data()
    text, reply_markup = language_screen(data.get("locale", "ru"))
    await show_command_screen(
        message=message,
        state=state,
        text=text,
        reply_markup=reply_markup,
    )


@other_router.callback_query(
    F.data.in_({"locale_en", "locale_es", "locale_ru", "locale_uk"})
)
async def update_locale_cmd(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18n,
    bot: Bot,
) -> None:
    """Сохранить язык и обновить тот же экран."""
    locale = normalize_locale(
        (callback.data or "locale_ru").removeprefix("locale_")
    )
    await orm_update_locale(session, callback.from_user.id, locale)
    await state.update_data(locale=locale)
    with i18n.use_locale(locale):
        text, reply_markup = language_screen(locale)
        try:
            new_message = await callback.message.edit_text(
                text=text,
                reply_markup=reply_markup,
            )
            await state.update_data(last_message_id=new_message.message_id)
        except TelegramBadRequest as error:
            if "message is not modified" not in error.message.lower():
                raise
        await callback.answer()
    try:
        await bot.set_my_commands(
            commands=PRIVATE_COMMANDS[locale],
            scope=BotCommandScopeChat(chat_id=callback.message.chat.id),
        )
    except TelegramAPIError:
        logger.exception("Не удалось обновить локализованное меню команд")


@other_router.message(Command("information"))
async def information_cmd(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Показать справку о боте в рабочем сообщении."""
    current_question = await orm_get_current_question(
        session, message.from_user.id
    )
    if current_question is None or current_question <= 13:
        buttons = {_("↩️ Назад"): "back_to_main"}
    else:
        buttons = {
            _("Поддержать проект"): "donate",
            _("↩️ Назад"): "back_to_main",
        }

    text = _(
        "ℹ️ О боте Factuality Test\n\n"
        "Интерактивный тест из 13 вопросов о глобальных трендах. "
        "Проверьте, насколько точно вы представляете "
        "реальное состояние мира.\n\n"
        "Как работает бот:\n"
        "• Вопросы появляются последовательно через inline-кнопки\n"
        "• Сообщения обновляются, а не множатся в чате\n"
        "• После прохождения теста доступны объяснения ответов\n\n"
        "Важное уточнение:\n"
        "Книга и основанный на ней тест написаны в 2015 году. Сейчас 2025, "
        "за 10 лет некоторые цифры изменились (например, население Земли "
        "выросло с 7 до 8 млрд). Однако суть осталась той же — тест про "
        "когнитивные искажения и инстинкты, а не про точные цифры. "
        "Тренды сохранились.\n\n"
        "Совет:\n"
        "Проходите тест интуитивно, не гуглите ответы — так вы увидите "
        "свои реальные представления о мире."
    )
    await show_command_screen(
        message=message,
        state=state,
        text=text,
        reply_markup=keyboard.get_callback_btns(
            btns=buttons,
            sizes=(1, 1),
        ),
    )


@other_router.message()
async def echo(message: Message) -> None:
    """Удалить неподдерживаемое пользовательское сообщение."""
    try:
        await message.delete()
    except TelegramBadRequest:
        logger.info("Не удалось удалить сообщение %s", message.message_id)
