"""Постоянный учёт платежей Telegram Stars."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payments


async def orm_record_payment(
    session: AsyncSession,
    charge_id: str,
    user_id: int,
    invoice_payload: str,
    currency: str,
    total_amount: int,
    paid_at: datetime | None = None,
) -> bool:
    """Записать платёж один раз и вернуть признак новой записи."""
    payment = await session.get(Payments, charge_id)
    if payment is not None:
        return False

    session.add(
        Payments(
            telegram_payment_charge_id=charge_id,
            user_id=user_id,
            invoice_payload=invoice_payload,
            currency=currency,
            total_amount=total_amount,
            paid_at=paid_at or datetime.now(timezone.utc),
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return False
    return True


async def orm_get_payment(
    session: AsyncSession,
    charge_id: str,
    user_id: int,
) -> Payments | None:
    """Получить принадлежащий пользователю платёж."""
    query = select(Payments).where(
        Payments.telegram_payment_charge_id == charge_id,
        Payments.user_id == user_id,
    )
    return (await session.execute(query)).scalar_one_or_none()


async def orm_mark_payment_refunded(
    session: AsyncSession,
    charge_id: str,
) -> None:
    """Отметить платёж возвращённым."""
    query = (
        update(Payments)
        .where(Payments.telegram_payment_charge_id == charge_id)
        .values(
            status="refunded",
            refunded_at=datetime.now(timezone.utc),
        )
    )
    await session.execute(query)
    await session.commit()
