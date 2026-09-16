"""Закрытые служебные команды администратора."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from filters.chat_type import ChatTypeFilter
from filters.is_admin import IsAdminListFilter

logger = logging.getLogger(__name__)

admin_router = Router()
admin_router.message.filter(ChatTypeFilter(["private"]), IsAdminListFilter(is_admin=True))

# секретный хендлер, покажет содержимое data пользователя
@admin_router.message(F.text == "..")
async def data_cmd(message: Message, state: FSMContext) -> None:
    """Показать администратору данные его FSM-состояния."""
    data = await state.get_data()
    await message.answer(str(data))
