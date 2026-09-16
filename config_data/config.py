"""Загрузка настроек приложения из переменных окружения."""

import logging
from dataclasses import dataclass

from environs import Env

logger = logging.getLogger(__name__)


@dataclass
class TgBot:
    """
    Класс для хранения информации о телеграм-боте.
    """
    token: str
    token_test: str | None
    owner: list[int]
    admin_list: list[int]
    home_group: list[int]
    work_group: list[int]

@dataclass
class DataBase:
    """
    Класс для хранения информации о базе данных
    """
    db_post: str
    db_lite: str

@dataclass
class Redis:
    """
    Класс для хранения информации о Redis
    """
    db: int
    host: str
    port: int
    password: str

@dataclass
class Config:
    """
    Основной класс конфигурации всего приложения
    """
    tg_bot: TgBot
    db: DataBase
    redis: Redis

# Функция загрузки конфигурации из файла окружения .env
def load_config(path: str | None = None) -> Config:
    env = Env()
    env.read_env(path)

    owner = map(int, env('OWNER').split(','))
    admin_list = map(int, env('ADMIN_LIST').split(','))
    home_group = map(int, env('HOME_GROUP').split(','))
    work_group = map(int, env('WORK_GROUP').split(','))

    return Config(
        tg_bot=TgBot(
            token=env('BOT_TOKEN'),
            token_test=env('BOT_TOKEN_TEST', None),  # Опциональный, для локальной разработки
            owner=list(owner),
            admin_list=list(admin_list),
            home_group=list(home_group),
            work_group=list(work_group),
            ),
        db=DataBase(
            db_post=env('DB_POST'),
            db_lite=env('DB_LITE')
            ),
        redis=Redis(
            host=env.str('REDIS_HOST'),
            port=env.int('REDIS_PORT'),
            db=env.int('REDIS_DB'),
            password=env.str('REDIS_PASSWORD'),
            )
        )
