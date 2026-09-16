"""Защита от мгновенных повторов одной inline-кнопки."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from cachetools import TTLCache

cache: TTLCache[tuple[int, str | None], bool] = TTLCache(
    maxsize=10_000,
    ttl=0.3,
)


class ThrottleMiddleware(BaseMiddleware):
    """Отбросить только мгновенный повтор той же callback-кнопки."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        callback = getattr(event, "callback_query", None)
        if callback is not None and callback.from_user is not None:
            key = (callback.from_user.id, callback.data)
            if key in cache:
                await callback.answer()
                return None
            cache[key] = True

        return await handler(event, data)
