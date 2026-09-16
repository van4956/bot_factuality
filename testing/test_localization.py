"""Проверки четырёх языков без Telegram и рабочих баз данных."""

from __future__ import annotations

import gettext
import re
import unittest
from pathlib import Path
from string import Formatter
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import EditMessageText, SetMyCommands
from aiogram.types import Message, Update
from aiogram.utils.i18n import I18n
from babel.messages.catalog import Catalog
from babel.messages.extract import extract
from babel.messages.pofile import read_po
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from common.comands import PRIVATE_COMMANDS
from common.locale import SUPPORTED_LOCALES, normalize_locale
from database.models import Base
from database.orm_answers import (
    CORRECT_ANSWERS,
    orm_get_answer,
    orm_get_progress,
    orm_save_answer,
)
from database.orm_users import orm_get_locale, orm_register_user
from handlers import factuality, other, start
from handlers.correct_answer import answer_options, correct_answers
from handlers.factuality import questions_answers
from handlers.inline import handle_inline_query
from handlers.other import language_screen, update_locale_cmd
from handlers.start import main_screen
from middlewares.db import DataBaseSession
from middlewares.locale import CachedLocaleMiddleware, LocaleFromDBMiddleware
from middlewares.screen import CurrentScreenMiddleware

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "bot_06_factuality"
LOCALES = ("en", "ru", "es", "uk")


def load_catalog(locale: str) -> Catalog:
    """Прочитать переводимый каталог."""
    path = ROOT / "locales" / locale / "LC_MESSAGES" / f"{DOMAIN}.po"
    with path.open(encoding="utf-8") as file:
        return read_po(file, locale=locale)


def placeholders(value: str) -> list[tuple[str, str, str | None]]:
    """Получить переменные форматирования и их спецификации."""
    return sorted(
        (name, specification, conversion)
        for _, name, specification, conversion in Formatter().parse(value)
        if name is not None
    )


class CatalogTests(unittest.TestCase):
    """Проверки полноты каталогов и переводимых экранов."""

    def setUp(self) -> None:
        """Загрузить каталоги и контекст перевода."""
        self.catalogs = {locale: load_catalog(locale) for locale in LOCALES}
        self.i18n = I18n(
            path=ROOT / "locales", default_locale="ru", domain=DOMAIN
        )

    def test_locale_normalization(self) -> None:
        """Поддерживать региональные коды и безопасный язык по умолчанию."""
        cases = {
            "es-MX": "es",
            "ES_es": "es",
            "uk-UA": "uk",
            "uk_UA": "uk",
            "en-US": "en",
            "ru-RU": "ru",
            "ua": "ru",
            "de": "ru",
            None: "ru",
            "": "ru",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_locale(value), expected)
        self.assertEqual(SUPPORTED_LOCALES, set(LOCALES))

    def test_catalog_coverage(self) -> None:
        """Каждая локаль содержит все актуальные строки исходного кода."""
        with (ROOT / "locales" / "messages.pot").open(
            encoding="utf-8"
        ) as file:
            template = read_po(file)
        expected = {message.id for message in template if message.id}
        for locale, catalog in self.catalogs.items():
            with self.subTest(locale=locale):
                self.assertEqual(
                    {message.id for message in catalog if message.id}, expected
                )
        for directory in ("common", "handlers", "middlewares"):
            for path in (ROOT / directory).rglob("*.py"):
                with path.open("rb") as file:
                    messages = extract(
                        "python", file, keywords={"_": None, "__": None}
                    )
                    for line, message, _, _ in messages:
                        with self.subTest(path=str(path), line=line):
                            self.assertIn(message, expected)

    def test_no_empty_or_fuzzy_translations(self) -> None:
        """Все пользовательские строки переведены и прошли проверки Babel."""
        for locale, catalog in self.catalogs.items():
            for message in catalog:
                if not message.id:
                    continue
                with self.subTest(locale=locale, message=message.id[:70]):
                    self.assertTrue(message.string)
                    self.assertNotIn("fuzzy", message.flags)
                    self.assertEqual(message.check(catalog), [])

    def test_placeholders_and_html(self) -> None:
        """Переводы сохраняют переменные и HTML-разметку исходных сообщений."""
        for locale, catalog in self.catalogs.items():
            for message in catalog:
                if not message.id:
                    continue
                with self.subTest(locale=locale, message=message.id[:70]):
                    self.assertEqual(
                        placeholders(message.id), placeholders(message.string)
                    )
                    self.assertEqual(
                        re.findall(r"</?[a-z]+[^>]*>", message.id),
                        re.findall(r"</?[a-z]+[^>]*>", message.string),
                    )
                    self.assertLessEqual(len(message.string), 4096)

    def test_compiled_catalogs_match_sources(self) -> None:
        """Бот загружает именно актуальные переводы из MO-файлов."""
        for locale, catalog in self.catalogs.items():
            path = ROOT / "locales" / locale / "LC_MESSAGES" / f"{DOMAIN}.mo"
            with path.open("rb") as file:
                translation = gettext.GNUTranslations(file)
            for message in catalog:
                if message.id:
                    with self.subTest(locale=locale, message=message.id[:70]):
                        self.assertEqual(
                            translation.gettext(message.id), message.string
                        )

    def test_language_screen_and_commands(self) -> None:
        """Сохранять два ряда языков и локализованные команды."""
        expected = [
            ["locale_en", "locale_ru"],
            ["locale_es", "locale_uk"],
            ["back_to_main"],
        ]
        for locale in LOCALES:
            with self.subTest(locale=locale):
                with self.i18n.context(), self.i18n.use_locale(locale):
                    text, markup = language_screen(locale)
                    self.assertNotIn("{language}", text)
                    self.assertEqual(
                        [
                            [button.callback_data for button in row]
                            for row in markup.inline_keyboard
                        ],
                        expected,
                    )
                    self.assertTrue(
                        all(
                            1 <= len(button.text) <= 64
                            for row in markup.inline_keyboard
                            for button in row
                        )
                    )
                    commands = PRIVATE_COMMANDS[locale]
                    self.assertEqual(
                        [command.command for command in commands],
                        ["information", "language"],
                    )
                    self.assertTrue(
                        all(
                            1 <= len(command.description) <= 256
                            for command in commands
                        )
                    )

    def test_questions_options_and_explanations(self) -> None:
        """Переводить все 13 вопросов без изменения идентификаторов ответов."""
        for locale in LOCALES:
            with self.i18n.context(), self.i18n.use_locale(locale):
                for number, (question, buttons) in questions_answers.items():
                    with self.subTest(locale=locale, question=number):
                        self.assertTrue(str(question))
                        self.assertEqual(
                            list(buttons),
                            [
                                f"question{number}_{answer}"
                                for answer in (1, 2, 3)
                            ],
                        )
                        explanation = str(correct_answers[number]).format(
                            user_answer=str(answer_options[number][1])
                        )
                        self.assertNotIn("{user_answer}", explanation)
                        for answer in (1, 2, 3):
                            value = str(answer_options[number][answer])
                            self.assertEqual(
                                str(buttons[f"question{number}_{answer}"]),
                                f"{answer}) {value}",
                            )
                            self.assertIn(f"{answer}) {value}", explanation)

    def test_main_screens(self) -> None:
        """Переводить старт, продолжение и завершение теста."""
        for locale in LOCALES:
            with self.i18n.context(), self.i18n.use_locale(locale):
                for question, result in ((1, None), (5, None), (14, 9)):
                    with self.subTest(locale=locale, question=question):
                        text, markup = main_screen(question, result)
                        self.assertNotIn("{correct_count}", text)
                        self.assertNotIn("{current_question}", text)
                        self.assertTrue(markup.inline_keyboard)
                        if question == 14:
                            self.assertIn("9/13", text)


class LanguageFlowTests(unittest.IsolatedAsyncioTestCase):
    """Проверки сохранения языка и прогресса в изолированной базе."""

    async def asyncSetUp(self) -> None:
        """Создать временную БД в памяти и отдельное FSM-хранилище."""
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.storage = MemoryStorage()
        self.state = FSMContext(
            storage=self.storage,
            key=StorageKey(bot_id=1, chat_id=123, user_id=123),
        )
        self.i18n = I18n(
            path=ROOT / "locales", default_locale="ru", domain=DOMAIN
        )
        self.bot = SimpleNamespace(set_my_commands=AsyncMock())
        self.callback = SimpleNamespace(
            data="locale_ru",
            from_user=SimpleNamespace(id=123),
            message=SimpleNamespace(
                chat=SimpleNamespace(id=123),
                edit_text=AsyncMock(
                    return_value=SimpleNamespace(message_id=456)
                ),
            ),
            answer=AsyncMock(),
        )
        async with self.sessions() as session:
            await orm_register_user(
                session,
                {
                    "user_id": 123,
                    "user_name": "test",
                    "full_name": "Test",
                    "locale": "ru",
                    "status": "member",
                    "flag": 1,
                },
            )

    async def asyncTearDown(self) -> None:
        """Освободить временные ресурсы."""
        await self.storage.close()
        await self.engine.dispose()

    async def test_switching_languages_preserves_all_answers(self) -> None:
        """Языковые переходы не сбрасывают ответы и завершённый результат."""
        await self.state.update_data(current_question=1, last_message_id=456)
        async with self.sessions() as session:
            for number in range(1, 14):
                locale = LOCALES[(number - 1) % len(LOCALES)]
                self.callback.data = f"locale_{locale}"
                with self.i18n.context(), self.i18n.use_locale("ru"):
                    await update_locale_cmd(
                        self.callback, session, self.state, self.i18n, self.bot
                    )
                    with self.i18n.use_locale(locale):
                        expected_text, _ = language_screen(locale)
                self.assertEqual(
                    self.callback.message.edit_text.call_args.kwargs["text"],
                    expected_text,
                )
                self.assertEqual(await orm_get_locale(session, 123), locale)
                self.assertEqual(
                    (await self.state.get_data())["locale"], locale
                )
                self.assertEqual(
                    (await self.state.get_data())["last_message_id"], 456
                )
                commands = self.bot.set_my_commands.call_args.kwargs
                self.assertEqual(
                    commands["commands"], PRIVATE_COMMANDS[locale]
                )
                self.assertEqual(commands["scope"].chat_id, 123)
                self.assertEqual(
                    await orm_get_progress(session, 123), (number, None)
                )
                await orm_save_answer(
                    session, 123, number, CORRECT_ANSWERS[number], 0.5
                )
            self.assertEqual(await orm_get_progress(session, 123), (14, 13))
            row = await orm_get_answer(session, 123)
            for number in range(1, 14):
                self.assertEqual(
                    getattr(row, f"answer_{number}"), CORRECT_ANSWERS[number]
                )

        # После очистки Redis/FSM выбранная локаль восстанавливается из БД.
        await self.state.clear()
        async with self.sessions() as session:
            event = SimpleNamespace(
                message=SimpleNamespace(
                    from_user=SimpleNamespace(id=123, language_code="es-MX")
                )
            )
            data = {"state": self.state, "session": session}
            await LocaleFromDBMiddleware()(AsyncMock(), event, data)
            self.assertEqual(data["fsm_data"]["locale"], "en")
            self.assertEqual(await orm_get_progress(session, 123), (14, 13))

    async def test_inline_locale_without_fsm(self) -> None:
        """Определять язык инлайн-запросов, даже когда у них нет FSM."""
        for saved_locale, telegram_locale, expected in (
            ("es", "en", "es"),
            (None, "uk-UA", "uk"),
        ):
            event = SimpleNamespace(
                inline_query=SimpleNamespace(
                    from_user=SimpleNamespace(
                        id=123, language_code=telegram_locale
                    )
                )
            )
            data = {"session": object()}
            with patch(
                "middlewares.locale.orm_get_locale",
                new=AsyncMock(return_value=saved_locale),
            ):
                await LocaleFromDBMiddleware()(AsyncMock(), event, data)
            self.assertEqual(
                await CachedLocaleMiddleware(self.i18n).get_locale(
                    event, data
                ),
                expected,
            )

    async def test_dispatcher_language_and_question_navigation(self) -> None:
        """Пройти реальные роутеры с подменённым Telegram API."""
        bot = Bot(token="123456:LOCAL_TEST_TOKEN")
        bot.home_group = [0]
        dispatcher = Dispatcher(storage=self.storage)
        dispatcher.update.outer_middleware(DataBaseSession(self.sessions))
        dispatcher.update.outer_middleware(LocaleFromDBMiddleware())
        dispatcher.update.outer_middleware(CurrentScreenMiddleware(self.i18n))
        dispatcher.update.middleware(CachedLocaleMiddleware(self.i18n))
        dispatcher.include_router(start.start_router)
        dispatcher.include_router(factuality.factuality_router)
        dispatcher.include_router(other.other_router)
        requests: list[Any] = []
        user = {
            "id": 123,
            "is_bot": False,
            "first_name": "Test",
            "language_code": "ru",
        }
        chat = {"id": 123, "type": "private"}

        async def respond(
            request_bot: Bot, method: Any, timeout: int | None = None
        ) -> Any:
            """Вернуть локальный ответ вместо сетевого запроса Telegram."""
            requests.append(method)
            if method.__api_method__ in {"sendMessage", "editMessageText"}:
                return Message.model_validate(
                    {
                        "message_id": 456,
                        "date": 0,
                        "chat": chat,
                        "text": method.text,
                    }
                ).as_(request_bot)
            return True

        actions = [
            ("message", "/start"),
            ("message", "/language"),
            ("callback", "locale_es"),
            ("callback", "back_to_main"),
            ("callback", "start_test"),
            ("callback", "question1_1"),
            ("message", "/language"),
            ("callback", "locale_uk"),
            ("callback", "back_to_main"),
            ("callback", "continue_test"),
            ("callback", "question2_2"),
        ]
        try:
            with patch.object(
                bot.session, "make_request", new=AsyncMock(side_effect=respond)
            ):
                for number, (kind, value) in enumerate(actions, start=1):
                    payload: dict[str, Any] = {"update_id": number}
                    if kind == "message":
                        payload["message"] = {
                            "message_id": number,
                            "date": 0,
                            "chat": chat,
                            "from": user,
                            "text": value,
                        }
                    else:
                        payload["callback_query"] = {
                            "id": str(number),
                            "from": user,
                            "chat_instance": "test",
                            "data": value,
                            "message": {
                                "message_id": 456,
                                "date": 0,
                                "chat": chat,
                                "text": "test",
                            },
                        }
                    await dispatcher.feed_update(
                        bot, Update.model_validate(payload)
                    )
            edits = [
                request
                for request in requests
                if request.__api_method__ == "editMessageText"
            ]
            with self.i18n.context(), self.i18n.use_locale("uk"):
                self.assertEqual(edits[-1].text, str(questions_answers[3][0]))
            self.assertEqual(
                sum(
                    request.__api_method__ == "sendMessage"
                    for request in requests
                ),
                1,
            )
            self.assertEqual(
                sum(
                    request.__api_method__ == "setMyCommands"
                    for request in requests
                ),
                2,
            )
            async with self.sessions() as session:
                self.assertEqual(
                    await orm_get_progress(session, 123), (3, None)
                )
                self.assertEqual(await orm_get_locale(session, 123), "uk")
        finally:
            await bot.session.close()

    async def test_repeated_selection(self) -> None:
        """Повторный выбор языка не вызывает ошибку неизменённого сообщения."""
        self.callback.message.edit_text.side_effect = TelegramBadRequest(
            method=EditMessageText(chat_id=123, message_id=456, text="test"),
            message="Bad Request: message is not modified",
        )
        async with self.sessions() as session:
            with self.i18n.context():
                await update_locale_cmd(
                    self.callback, session, self.state, self.i18n, self.bot
                )
            self.assertEqual(await orm_get_locale(session, 123), "ru")
            self.callback.answer.assert_awaited_once()

    async def test_command_menu_failure_does_not_revert_locale(self) -> None:
        """Сетевой сбой меню команд не отменяет сохранённый язык."""
        self.callback.data = "locale_uk"
        self.bot.set_my_commands.side_effect = TelegramNetworkError(
            method=SetMyCommands(commands=[]), message="test failure"
        )
        async with self.sessions() as session:
            with (
                self.i18n.context(),
                self.assertLogs("handlers.other", "ERROR"),
            ):
                await update_locale_cmd(
                    self.callback, session, self.state, self.i18n, self.bot
                )
            self.assertEqual(await orm_get_locale(session, 123), "uk")
            self.callback.answer.assert_awaited_once()

    async def test_inline_results_are_personal_and_localized(self) -> None:
        """Не разделять языковой кеш инлайн-карточек между пользователями."""
        for locale in LOCALES:
            query = SimpleNamespace(answer=AsyncMock())
            with self.i18n.context(), self.i18n.use_locale(locale):
                await handle_inline_query(query)
                expected = self.i18n.gettext(
                    "Проверьте своё понимание глобальных тенденций"
                )
            result = query.answer.call_args.args[0][0]
            self.assertEqual(result.description, expected)
            self.assertTrue(query.answer.call_args.kwargs["is_personal"])

    async def test_stale_screen_alert_in_all_languages(self) -> None:
        """Переводить предупреждение до установки контекста gettext."""
        for locale in LOCALES:
            callback = SimpleNamespace(
                message=SimpleNamespace(
                    message_id=1, edit_reply_markup=AsyncMock()
                ),
                answer=AsyncMock(),
            )
            handler = AsyncMock()
            await CurrentScreenMiddleware(self.i18n)(
                handler,
                SimpleNamespace(callback_query=callback),
                {
                    "state": self.state,
                    "fsm_data": {"locale": locale, "last_message_id": 456},
                },
            )
            callback.answer.assert_awaited_once_with(
                self.i18n.gettext(
                    "Это меню устарело. Используйте последнее сообщение бота.",
                    locale=locale,
                ),
                show_alert=True,
            )
            handler.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
