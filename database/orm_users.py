"""Операции с пользователями."""

import logging
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Answers, Users
from database.orm_answers import repair_answer_progress

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserRegistrationResult:
    """Результат регистрации и сохранённый прогресс теста."""

    is_new: bool
    current_question: int
    result: int | None


async def orm_register_user(
    session: AsyncSession,
    data: dict,
) -> UserRegistrationResult:
    """Создать пользователя и сразу вернуть его прогресс."""
    query = (
        select(Users, Answers)
        .outerjoin(Answers, Answers.user_id == Users.user_id)
        .where(Users.user_id == data["user_id"])
    )
    existing = (await session.execute(query)).one_or_none()
    if existing is not None:
        answer_row = existing[1]
        if answer_row is None:
            session.add(Answers(user_id=data["user_id"], current_question=1))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
            return UserRegistrationResult(False, 1, None)
        if repair_answer_progress(answer_row):
            await session.commit()
        return UserRegistrationResult(False, answer_row.current_question, answer_row.result)

    session.add(
        Users(
            user_id=data["user_id"],
            user_name=data["user_name"],
            full_name=data["full_name"],
            locale=data["locale"],
            status=data["status"],
            flag=data["flag"],
        )
    )
    try:
        # Без ORM-связи SQLAlchemy не обязан сам определить порядок INSERT.
        # Сначала гарантированно создаём родительскую строку пользователя.
        await session.flush()
        session.add(Answers(user_id=data["user_id"], current_question=1))
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = (await session.execute(query)).one_or_none()
        if existing is None:
            raise

        answer_row = existing[1]
        if answer_row is None:
            session.add(Answers(user_id=data["user_id"], current_question=1))
            await session.commit()
            return UserRegistrationResult(False, 1, None)

        if repair_answer_progress(answer_row):
            await session.commit()
        return UserRegistrationResult(
            False,
            answer_row.current_question,
            answer_row.result,
        )
    return UserRegistrationResult(True, 1, None)

# получаем одного юзера по его user_id
async def orm_get_user(session: AsyncSession, user_id: int) -> Users | None:
    """Получить пользователя по идентификатору Telegram."""
    query = select(Users).where(Users.user_id == user_id)
    result = await session.execute(query)
    return result.scalar()

# получаем локаль юзера по user_id
async def orm_get_locale(session: AsyncSession, user_id: int) -> str | None:
    """Получить выбранную пользователем локаль."""
    query = select(Users.locale).where(Users.user_id == user_id)
    result = await session.execute(query)
    return result.scalar()

# изменение статуса юзера
async def orm_update_status(
    session: AsyncSession,
    user_id: int,
    data: str,
) -> None:
    """Обновить статус пользователя."""
    query = update(Users).where(Users.user_id == user_id).values(status=data)
    await session.execute(query)
    await session.commit()

# изменение locale юзера
async def orm_update_locale(
    session: AsyncSession,
    user_id: int,
    data: str,
) -> None:
    """Обновить локаль пользователя."""
    query = update(Users).where(Users.user_id == user_id).values(locale=data)
    await session.execute(query)
    await session.commit()
