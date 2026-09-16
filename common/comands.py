"""Локализованные команды Telegram-бота."""

from aiogram.types import BotCommand

PRIVATE_COMMANDS: dict[str, list[BotCommand]] = {
    "en": [
        BotCommand(command="information", description="About the bot"),
        BotCommand(command="language", description="Change language"),
    ],
    "es": [
        BotCommand(command="information", description="Acerca del bot"),
        BotCommand(command="language", description="Cambiar idioma"),
    ],
    "ru": [
        BotCommand(command="information", description="О боте"),
        BotCommand(command="language", description="Изменить язык"),
    ],
    "uk": [
        BotCommand(command="information", description="Про бота"),
        BotCommand(command="language", description="Змінити мову"),
    ],
}
