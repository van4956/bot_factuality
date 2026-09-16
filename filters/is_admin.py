"""Фильтры прав администратора."""

from aiogram import Bot
from aiogram.filters import BaseFilter
from aiogram.types import Message


class IsAdminGroupFilter(BaseFilter):
    """Проверить наличие прав администратора в группе."""

    def __init__(self, is_admin: bool) -> None:
        self.is_admin = is_admin

    async def __call__(self, message: Message) -> bool:
        member = await message.bot.get_chat_member(
            message.chat.id,
            message.from_user.id,
        )
        return member.is_chat_admin() == self.is_admin


class IsAdminListFilter(BaseFilter):
    """Проверить наличие пользователя в настроенном списке администраторов."""

    def __init__(self, is_admin: bool) -> None:
        self.is_admin = is_admin

    async def __call__(self, message: Message, bot: Bot) -> bool:
        in_admin_list = message.from_user.id in bot.admin_list
        return in_admin_list == self.is_admin
