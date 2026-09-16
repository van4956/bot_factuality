"""Точка запуска Telegram-бота."""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.strategy import FSMStrategy
from aiogram.utils.i18n import I18n
from influxdb_client import InfluxDBClient, Point  # type: ignore
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from common.comands import private
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

ANALYTICS_QUEUE_SIZE = 10_000
analytics_queue: asyncio.Queue[Point | None] = asyncio.Queue(
    maxsize=ANALYTICS_QUEUE_SIZE
)
analytics_client: InfluxDBClient | None = None
analytics_worker_task: asyncio.Task[None] | None = None

# Инициализируем функцию для сбора аналитики, взаимодействуем с InfluxDB и Grafana
async def analytics(
    user_id: int,
    command_name: str,
    category_name: str,
) -> None:
    """Поставить событие аналитики в неблокирующую очередь."""
    if docker != 1:
        return

    point = (
        Point("bot_command_usage")
        .tag("category", category_name)
        .tag("command", command_name)
        .tag("user_id", str(user_id))
        .tag("ping", "ping")
        .time(datetime.now(timezone.utc))
        .field("value", 1)
    )
    try:
        analytics_queue.put_nowait(point)
    except asyncio.QueueFull:
        logger.warning("Очередь аналитики заполнена; событие пропущено")


async def analytics_worker() -> None:
    """Записывать события InfluxDB вне цикла обработки Telegram."""
    if analytics_client is None:
        return

    write_api = analytics_client.write_api(write_options=SYNCHRONOUS)
    while True:
        point = await analytics_queue.get()
        try:
            if point is None:
                return
            await asyncio.to_thread(
                write_api.write,
                bucket=config.influx.bucket,
                org=config.influx.org,
                record=point,
            )
        except (ConnectionError, TimeoutError, ApiException):
            logger.exception("Не удалось записать событие в InfluxDB")
        except Exception:
            logger.exception("Непредвиденная ошибка записи аналитики")
        finally:
            analytics_queue.task_done()


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


# Помещаем нужные объекты в workflow_data диспетчера
some_var_1 = 1
some_var_2 = 'Some text'
dp.workflow_data.update({'my_int_var': some_var_1,
                         'my_text_var': some_var_2,
                         'analytics': analytics})


# Подключаем мидлвари
dp.update.outer_middleware(throttle.ThrottleMiddleware())  # тротлинг чрезмерно частых действий пользователей
dp.update.outer_middleware(db.DataBaseSession(session_pool=session_maker))  # мидлварь для прокидывания сессии БД
dp.update.outer_middleware(locale.LocaleFromDBMiddleware(workflow_data=dp.workflow_data))  # определяем локаль из БД и передам ее в FSMContext
dp.update.outer_middleware(screen.CurrentScreenMiddleware())
i18n = I18n(path="locales", default_locale="ru", domain="bot_06_factuality")  # создаем объект I18n
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
    """Подготовить внешние клиенты и сверить платежи."""
    global analytics_client, analytics_worker_task

    if docker == 1:
        analytics_client = InfluxDBClient(
            url=config.influx.url,
            token=config.influx.token,
            org=config.influx.org,
            timeout=2_000,
        )
        analytics_worker_task = asyncio.create_task(analytics_worker())

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

    if analytics_worker_task is not None:
        await analytics_queue.put(None)
        try:
            await asyncio.wait_for(analytics_queue.join(), timeout=5)
        except TimeoutError:
            analytics_worker_task.cancel()
        await asyncio.gather(analytics_worker_task, return_exceptions=True)
    if analytics_client is not None:
        await asyncio.to_thread(analytics_client.close)
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

    # Удаляем ранее установленные команды для бота во всех личных чатах
    await bot.delete_my_commands(scope=types.BotCommandScopeAllPrivateChats())

    # Добавляем свои команды
    await bot.set_my_commands(commands=private, scope=types.BotCommandScopeAllPrivateChats())


    # Запускаем polling
    try:
        await dp.start_polling(bot,
                               allowed_updates=ALLOWED_UPDATES,)
                            #    skip_updates=False)  # Если бот будет обрабатывать платежи, НЕ пропускаем обновления!
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
