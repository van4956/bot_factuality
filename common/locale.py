"""Нормализация поддерживаемых локалей бота."""

SUPPORTED_LOCALES = {"en", "ru"}


def normalize_locale(value: str | None) -> str:
    """Вернуть поддерживаемый код языка или русский по умолчанию."""
    language = (value or "ru").lower().split("-", maxsplit=1)[0]
    language = language.split("_", maxsplit=1)[0]
    return language if language in SUPPORTED_LOCALES else "ru"
