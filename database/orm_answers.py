"""Операции с ответами пользователей."""

import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Answers

logger = logging.getLogger(__name__)

CORRECT_ANSWERS: dict[int, int] = {
    1: 3,
    2: 2,
    3: 3,
    4: 3,
    5: 3,
    6: 2,
    7: 3,
    8: 1,
    9: 3,
    10: 1,
    11: 3,
    12: 3,
    13: 1,
}


@dataclass(frozen=True)
class AnswerSaveResult:
    """Результат атомарного сохранения одного ответа."""

    accepted: bool
    next_question: int | None
    result: int | None = None
    total_time: float | None = None


def repair_answer_progress(row: Answers) -> bool:
    """Исправить незавершённую финализацию без потери ответов."""
    if row.current_question <= 13:
        return False

    first_missing = next(
        (
            number
            for number in range(1, 14)
            if getattr(row, f"answer_{number}") is None
        ),
        None,
    )
    if first_missing is not None:
        row.current_question = first_missing
        row.result = None
        row.answer_total_time = None
        return True

    expected_result = sum(
        getattr(row, f"answer_{number}") == CORRECT_ANSWERS[number]
        for number in range(1, 14)
    )
    expected_total_time = round(
        sum(
            getattr(row, f"answer_{number}_time") or 0.0
            for number in range(1, 14)
        ),
        2,
    )
    changed = (
        row.current_question != 14
        or row.result != expected_result
        or row.answer_total_time != expected_total_time
    )
    row.current_question = 14
    row.result = expected_result
    row.answer_total_time = expected_total_time
    return changed

# получаем все ответы юзера
async def orm_get_answer(session: AsyncSession, user_id: int) -> Answers | None:
    query = select(Answers).where(Answers.user_id == user_id)
    result = await session.execute(query)
    return result.scalar()

# получаем текущий вопрос юзера
async def orm_get_current_question(session: AsyncSession, user_id: int) -> int | None:
    query = select(Answers.current_question).where(Answers.user_id == user_id)
    result = await session.execute(query)
    return result.scalar()

async def orm_get_progress(
    session: AsyncSession,
    user_id: int,
) -> tuple[int | None, int | None]:
    """Получить прогресс и исправить старую незавершённую финализацию."""
    query = select(Answers).where(Answers.user_id == user_id)
    row = (await session.execute(query)).scalar_one_or_none()
    if row is None:
        return None, None
    if repair_answer_progress(row):
        await session.commit()
    return row.current_question, row.result

async def orm_save_answer(
    session: AsyncSession,
    user_id: int,
    question: int,
    answer: int,
    answer_time: float,
    correct_answers: dict[int, int] = CORRECT_ANSWERS,
) -> AnswerSaveResult:
    """Атомарно сохранить ответ и продвинуть тест."""
    if question not in range(1, 14):
        raise ValueError("Номер вопроса должен быть от 1 до 13")
    if answer not in {1, 2, 3}:
        raise ValueError("Номер ответа должен быть от 1 до 3")
    if answer_time < 0:
        raise ValueError("Время ответа не может быть отрицательным")

    query = (
        select(Answers)
        .where(Answers.user_id == user_id)
        .with_for_update()
    )
    row = (await session.execute(query)).scalar_one_or_none()

    if row is None:
        await session.rollback()
        return AnswerSaveResult(False, None)

    was_repaired = repair_answer_progress(row)
    if row.current_question != question:
        result = AnswerSaveResult(
            False,
            row.current_question,
            row.result,
            row.answer_total_time,
        )
        if was_repaired:
            await session.commit()
        else:
            await session.rollback()
        return result

    setattr(row, f"answer_{question}", answer)
    setattr(row, f"answer_{question}_time", answer_time)
    row.current_question = question + 1

    if question < 13:
        await session.commit()
        return AnswerSaveResult(True, row.current_question)

    row.result = sum(
        getattr(row, f"answer_{number}") == correct_answers[number]
        for number in range(1, 14)
    )
    row.answer_total_time = round(
        sum(
            getattr(row, f"answer_{number}_time") or 0.0
            for number in range(1, 14)
        ),
        2,
    )
    await session.commit()
    return AnswerSaveResult(
        True,
        row.current_question,
        row.result,
        row.answer_total_time,
    )


async def orm_get_result_statistics(
    session: AsyncSession,
) -> tuple[int, float]:
    """Получить число завершённых тестов и средний результат."""
    query = select(func.count(Answers.result), func.avg(Answers.result)).where(
        Answers.result.is_not(None)
    )
    count, average = (await session.execute(query)).one()
    return int(count or 0), float(average or 0.0)
