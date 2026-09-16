"""Точка запуска Telegram-бота."""

import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.strategy import FSMStrategy
from aiogram.utils.i18n import I18n
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from common.comands import PRIVATE_COMMANDS
from config_data.config import Config, load_config
from database.models import Base
from handlers import (
    admin,
    correct_answer,
    donate,
    factuality,
    group,
    inline,
    other,
    start,
)
from middlewares import db, locale, screen, throttle

# Режим запуска:
# docker == 1 - это запуск в docker - docker-compose up -d
# docker == 0 - это запуск локально - ctrl + B
docker = 1

logging.basicConfig(
    level=logging.INFO,
    format=(
        "  -  [%(asctime)s] #%(levelname)-5s -  "
        "%(name)s:%(lineno)d  -  %(message)s"
    ),
)
logger = logging.getLogger(__name__)

sqlalchemy_logger = logging.getLogger("sqlalchemy.engine")
sqlalchemy_logger.setLevel(logging.WARNING)
sqlalchemy_logger.propagate = True

# Загружаем конфиг в переменную config
config: Config = load_config()


# Инициализируем объект хранилища
if docker == 1:
    # данные хранятся на отдельном сервере Redis
    storage = RedisStorage(
        redis=Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password,
        )
    )
    events_isolation = storage.create_isolation()
else:
    # данные хранятся в оперативной памяти (для тестов и разработки)
    storage = MemoryStorage()
    events_isolation = SimpleEventIsolation()

# Формируем токен бота в зависимости от режима работы
if docker == 1:
    token = config.tg_bot.token
else:
    token = config.tg_bot.token_test or config.tg_bot.token


logger.info('Инициализируем бот и диспетчер')
bot = Bot(token=token,
          default=DefaultBotProperties(parse_mode=ParseMode.HTML,
                                       link_preview=None,
                                       link_preview_is_disabled=None,
                                       link_preview_prefer_large_media=None,
                                       link_preview_prefer_small_media=None,
                                       link_preview_show_above_text=None))
bot.owner = config.tg_bot.owner
bot.admin_list = config.tg_bot.admin_list
bot.home_group = config.tg_bot.home_group
bot.work_group = config.tg_bot.work_group


dp = Dispatcher(
    fsm_strategy=FSMStrategy.USER_IN_CHAT,
    storage=storage,
    events_isolation=events_isolation,
)
# USER_IN_CHAT  -  для каждого юзера, в каждом чате ведется своя запись состояний (по дефолту)
# GLOBAL_USER  -  для каждого юзера везде ведется своё состояние


# Создаем движок бд
if docker == 1:
    # PostgreSQL
    engine = create_async_engine(
        config.db.db_post,
        echo=False,
        pool_pre_ping=True,
    )
else:
    # SQLite (для тестов и разработки)
    engine = create_async_engine(config.db.db_lite, echo=False)


# Создаем ассинхроную сессию
session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# Подключаем мидлвари
i18n = I18n(path="locales", default_locale="ru", domain="bot_06_factuality")
dp.update.outer_middleware(throttle.ThrottleMiddleware())  # тротлинг чрезмерно частых действий пользователей
dp.update.outer_middleware(db.DataBaseSession(session_pool=session_maker))  # мидлварь для прокидывания сессии БД
dp.update.outer_middleware(locale.LocaleFromDBMiddleware())  # определяем локаль из БД и передам ее в FSMContext
dp.update.outer_middleware(screen.CurrentScreenMiddleware(i18n=i18n))
dp.update.middleware(locale.CachedLocaleMiddleware(i18n=i18n))

# dp.update.middleware(ConstI18nMiddleware(locale='ru', i18n=i18n))  # задаем локаль как принудительно устанавливаемую константу
# dp.update.middleware(SimpleI18nMiddleware(i18n=i18n))  # задаем локаль по значению поля "language_code" апдейта

# Подключаем роутеры
dp.include_router(start.start_router)
dp.include_router(admin.admin_router)
dp.include_router(donate.donate_router)
dp.include_router(group.group_router)
dp.include_router(inline.inline_router)
dp.include_router(factuality.factuality_router)
dp.include_router(correct_answer.correct_answer_router)
dp.include_router(other.other_router)


# Типы апдейтов которые будем отлавливать ботом
# ALLOWED_UPDATES = ['message', 'edited_message', 'callback_query',]  # Отбираем определенные типы апдейтов
ALLOWED_UPDATES = dp.resolve_used_update_types()  # Отбираем только используемые события по роутерам

# Функция сработает при запуске бота
async def on_startup() -> None:
    """Сверить платежи и отправить служебное сообщение."""
    try:
        restored = await asyncio.wait_for(
            donate.reconcile_recent_payments(bot, session_maker),
            timeout=10,
        )
        if restored:
            logger.info("Восстановлено платежей из Telegram: %s", restored)
    except Exception:
        logger.exception("Не удалось сверить последние платежи Telegram")

    try:
        bot_info = await bot.get_me()
        await bot.send_message(
            chat_id=bot.home_group[0],
            text=f"🤖  @{bot_info.username}  -  запущен!",
        )
    except Exception:
        logger.exception("Не удалось отправить служебное сообщение о запуске")

# Функция сработает при остановке работы бота
async def on_shutdown() -> None:
    """Освободить ресурсы при остановке бота."""
    try:
        bot_info = await bot.get_me()
        await bot.send_message(
            chat_id=bot.home_group[0],
            text=f"☠️  @{bot_info.username}  -  деактивирован!",
        )
    except Exception:
        logger.exception(
            "Не удалось отправить служебное сообщение об остановке"
        )

    await engine.dispose()

# Главная функция конфигурирования и запуска бота
async def main() -> None:

    # Удаление предыдущей версии базы, и создание новых таблиц заново
    async with engine.begin() as connection:
        # await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    # Регистрируем функцию, которая будет вызвана автоматически при запуске/остановке бота
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Пропускаем накопившиеся апдейты - удаляем вебхуки (то что бот получил пока спал)
    await bot.delete_webhook(drop_pending_updates=False)

    commands_scope = types.BotCommandScopeAllPrivateChats()
    await bot.delete_my_commands(scope=commands_scope)
    await bot.set_my_commands(
        commands=PRIVATE_COMMANDS["ru"],
        scope=commands_scope,
    )
    for language_code, commands in PRIVATE_COMMANDS.items():
        await bot.set_my_commands(
            commands=commands,
            scope=commands_scope,
            language_code=language_code,
        )


    # Запускаем polling
    try:
        await dp.start_polling(bot,
                               allowed_updates=ALLOWED_UPDATES,)
                            #    skip_updates=False)  # Если бот будет обрабатывать платежи, НЕ пропускаем обновления!
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
