"""Обработка служебных сообщений в группах."""

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

logger = logging.getLogger(__name__)

group_router = Router()
group_router.message.filter(F.chat.type.in_({"group", "supergroup"}))


@group_router.message(
    F.content_type.in_({"new_chat_members", "left_chat_member"})
)
async def on_user_join_or_left(message: Message) -> None:
    """Удалить системное сообщение о входе или выходе участника."""
    try:
        await message.delete()
    except TelegramAPIError:
        logger.info("Не удалось удалить служебное сообщение в группе")
