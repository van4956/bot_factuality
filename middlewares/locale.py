"""Восстановление выбранной пользователем локали."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from aiogram.utils.i18n.middleware import I18nMiddleware

from common.locale import normalize_locale
from database.orm_users import orm_get_locale

logger = logging.getLogger(__name__)


def get_user(event: TelegramObject) -> User | None:
    """Получить пользователя из обновления Telegram."""
    for attribute in (
        "message",
        "callback_query",
        "edited_message",
        "inline_query",
        "chosen_inline_result",
        "chat_join_request",
        "chat_member",
        "my_chat_member",
        "pre_checkout_query",
        "shipping_query",
    ):
        payload = getattr(event, attribute, None)
        user = getattr(payload, "from_user", None)
        if user is not None:
            return user

    poll_answer = getattr(event, "poll_answer", None)
    return getattr(poll_answer, "user", None)


def get_user_id(event: TelegramObject) -> int | None:
    """Получить идентификатор пользователя из обновления Telegram."""
    user = get_user(event)
    return user.id if user is not None else None


class LocaleFromDBMiddleware(BaseMiddleware):
    """Загрузить локаль из БД, если её ещё нет в FSM."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            state = data.get("state")
            state_data = await state.get_data() if state else {}
            if not state_data.get("locale"):
                session = data.get("session")
                user = get_user(event)
                user_locale = None
                if session is not None and user is not None:
                    user_locale = await orm_get_locale(session, user.id)
                if user is not None:
                    user_locale = user_locale or user.language_code
                normalized_locale = normalize_locale(user_locale)
                if state:
                    await state.update_data(locale=normalized_locale)
                state_data["locale"] = normalized_locale
            data["fsm_data"] = state_data
        except Exception:
            logger.exception("Не удалось восстановить локаль пользователя")

        return await handler(event, data)


class CachedLocaleMiddleware(I18nMiddleware):
    """Использовать уже прочитанную из FSM локаль без второго запроса Redis."""

    async def get_locale(
        self,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> str:
        """Вернуть локаль, подготовленную внешним middleware."""
        state_data = data.get("fsm_data") or {}
        return normalize_locale(state_data.get("locale"))
