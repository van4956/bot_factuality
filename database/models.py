"""Модели постоянного хранилища бота."""

import logging
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    '''первичный класс, от него дальше будут наследоваться все остальные'''
    created: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
    )


class Users(Base):
    '''class Users соответствует таблице users в базе данных'''
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(150), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    locale: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(150), nullable=False)
    flag: Mapped[int] = mapped_column(Integer, nullable=False)  # тротлинг

class Answers(Base):
    '''class Answers соответствует таблице answers в базе данных'''
    __tablename__ = "answers"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True, autoincrement=True)
    current_question: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_1_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_2_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_3: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_3_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_4: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_4_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_5: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_5_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_6: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_6_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_7: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_7_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_8: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_8_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_9: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_9_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_10: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_10_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_11: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_11_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_12: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_12_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_13: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_13_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[int | None] = mapped_column(
        Integer,
        CheckConstraint("result >= 0 AND result <= 13"),
        nullable=True,
    )
    answer_total_time: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )


class Payments(Base):
    """Платежи Telegram Stars и их возвраты."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "total_amount > 0",
            name="ck_payments_total_amount_positive",
        ),
        CheckConstraint(
            "status IN ('paid', 'refunded')",
            name="ck_payments_status",
        ),
    )

    telegram_payment_charge_id: Mapped[str] = mapped_column(
        String(255), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    invoice_payload: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="paid"
    )
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
