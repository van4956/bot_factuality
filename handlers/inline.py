"""Инлайн-карточка с описанием бота."""

from typing import Sequence

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from aiogram.utils.i18n import gettext as _

# Создаем роутер для инлайн-режима
inline_router = Router()

# Инлайн-режим включается через BotFather:
# /mybots → Bot Settings → Inline Mode → Turn on.
# Там же задаётся текст подсказки в поле ввода.


@inline_router.inline_query()
async def handle_inline_query(inline_query: InlineQuery) -> None:
    """Вернуть карточку бота в инлайн-режиме."""
    # Создаем результат инлайн-запроса
    results: Sequence[InlineQueryResultArticle] = [
        InlineQueryResultArticle(
            id="1",
            title=_("Factuality Test"),
            description=_("Проверьте своё понимание глобальных тенденций"),
            input_message_content=InputTextMessageContent(
                message_text=_(
                    "🌍 Factuality Test\n\n"
                    "Тест по книге Ханса Рослинга «Фактологичность».\n"
                    "Проверьте, насколько точно вы воспринимаете мировые "
                    "тенденции.\n\n"
                    "Попробуйте: @factuality_test_bot"
                )
            ),
        )
    ]
    # Отправляем результаты
    await inline_query.answer(results, cache_time=300, is_personal=True)
