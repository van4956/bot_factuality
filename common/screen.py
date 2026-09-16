"""Обновление единственного рабочего сообщения бота."""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)


async def show_command_screen(
    message: Message,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> int:
    """Удалить команду и обновить рабочее сообщение или создать его."""
    try:
        await message.delete()
    except TelegramAPIError:
        logger.info("Не удалось удалить команду %s", message.message_id)

    data = await state.get_data()
    last_message_id = data.get("last_message_id")
    if last_message_id:
        try:
            edited = await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=last_message_id,
                text=text,
                reply_markup=reply_markup,
            )
            message_id = edited.message_id
            await state.update_data(last_message_id=message_id)
            return message_id
        except TelegramBadRequest as error:
            if "message is not modified" in error.message.lower():
                return int(last_message_id)
            logger.info(
                "Не удалось обновить рабочее сообщение %s: %s",
                last_message_id,
                error,
            )

    new_message = await message.answer(text=text, reply_markup=reply_markup)
    await state.update_data(last_message_id=new_message.message_id)
    return new_message.message_id
