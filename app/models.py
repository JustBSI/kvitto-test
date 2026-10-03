"""Database tables. Public validation schemas live separately from ORM models."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tariff(Base):
    __tablename__ = "tariffs"
    __table_args__ = (
        UniqueConstraint("title", name="uq_tariffs_title"),
        CheckConstraint("price > 0", name="ck_tariffs_price_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(50))
    price: Mapped[int] = mapped_column(BigInteger)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint("discount >= 0", name="ck_payments_discount_nonnegative"),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')",
            name="ck_payments_status",
        ),
        CheckConstraint(
            "(method IN ('card', 'sbp') AND installment_months IS NULL) OR "
            "(method = 'installment' AND installment_months IS NOT NULL "
            "AND installment_months IN (3, 6, 12))",
            name="ck_payments_method_months",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    discount: Mapped[int] = mapped_column(BigInteger)
    method: Mapped[str] = mapped_column(String(20))
    installment_months: Mapped[int | None] = mapped_column(Integer)
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
