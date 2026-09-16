"""Фильтр типа Telegram-чата."""

from aiogram.filters import BaseFilter
from aiogram.types import Message


class ChatTypeFilter(BaseFilter):
    """Пропустить сообщения только из указанных типов чатов."""

    def __init__(self, chat_type: str | list[str]) -> None:
        self.chat_type = chat_type

    async def __call__(self, message: Message) -> bool:
        if isinstance(self.chat_type, str):
            return message.chat.type == self.chat_type
        return message.chat.type in self.chat_type
