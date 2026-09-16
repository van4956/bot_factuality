"""Защита от кнопок устаревших сообщений."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class CurrentScreenMiddleware(BaseMiddleware):
    """Пропускать кнопки только последнего рабочего сообщения."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        callback = getattr(event, "callback_query", None)
        state = data.get("state")
        if callback is None or callback.message is None or state is None:
            return await handler(event, data)

        state_data = data.get("fsm_data")
        if state_data is None:
            state_data = await state.get_data()
        last_message_id = state_data.get("last_message_id")
        if not last_message_id or callback.message.message_id == last_message_id:
            return await handler(event, data)

        if state_data.get("locale") == "en":
            alert = "This menu is outdated. Use the latest bot message."
        else:
            alert = "Это меню устарело. Используйте последнее сообщение бота."
        await callback.answer(alert, show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            logger.info(
                "Не удалось отключить старую клавиатуру %s",
                callback.message.message_id,
            )
        return None
