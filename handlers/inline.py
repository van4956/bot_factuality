import logging

# Инициализируем логгер модуля
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.info("Загружен модуль: %s", __name__)

from typing import Sequence
from aiogram import F, Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

# Создаем роутер для инлайн-режима
inline_router = Router()

"""Для включения инлайн-режима у бота нужно, включить инлайн-режим через BotFather:
1. Найти @BotFather в Telegram
2. Отправить команду /mybots
3. Выбрать текущего бота
4. Выбрать "Bot Settings"
5. Выбрать "Inline Mode"
6. Включить инлайн-режим ("Turn on")
7. Установите placeholder text (текст, который будет отображаться в поле ввода)"""

@inline_router.inline_query()
async def handle_inline_query(inline_query: InlineQuery) -> None:
    """Вернуть карточку бота в инлайн-режиме."""
    # Создаем результат инлайн-запроса
    results: Sequence[InlineQueryResultArticle] = [
        InlineQueryResultArticle(
            id="1",
            title="Factuality Test",
            description="Test your understanding of global trends",
            input_message_content=InputTextMessageContent(
                message_text="🌍 Factuality Test\n\n"
                            "A test from the book 'Factuality' by Hans Rosling.\n"
                            "Check how accurately you perceive world trends.\n\n"
                            "Try: @factuality_test_bot"
            )
        )
    ]
    # Отправляем результаты
    await inline_query.answer(results, cache_time=300) # type: ignore
