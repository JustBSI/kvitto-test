"""Concrete database operations; each writing operation owns one transaction."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.business import PaymentStatus, calculate_amount, can_transition
from app.models import Payment, Tariff
from app.schemas import PaymentCreate


class TariffNotFound(Exception):
    pass


class PaymentNotFound(Exception):
    pass


class InvalidTransition(Exception):
    pass


async def create_payment(
    session: AsyncSession, data: PaymentCreate, idempotency_key: str | None
) -> tuple[Payment, bool]:
    """Return (payment, created). UNIQUE is the authority under concurrent requests."""
    async with session.begin():
        if idempotency_key is not None:
            existing = await session.scalar(
                select(Payment).where(Payment.idempotency_key == idempotency_key)
            )
            if existing is not None:
                return existing, False

        tariff = await session.get(Tariff, data.tariff_id)
        if tariff is None:
            raise TariffNotFound
        amount, discount = calculate_amount(tariff.price, data.promo_code)
        statement = insert(Payment).values(
            tariff_id=tariff.id,
            email=str(data.email),
            method=data.method.value,
            installment_months=data.installment_months,
            amount=amount,
            discount=discount,
            idempotency_key=idempotency_key,
        )
        if idempotency_key is not None:
            statement = statement.on_conflict_do_nothing(
                constraint="uq_payments_idempotency_key"
            )
        payment = await session.scalar(statement.returning(Payment))
        if payment is not None:
            return payment, True

        # ON CONFLICT waits for the winner to commit. A new SELECT sees its row
        # under PostgreSQL's default READ COMMITTED isolation level.
        existing = await session.scalar(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise RuntimeError("Conflicting payment was not found")
        return existing, False


async def get_payment(session: AsyncSession, payment_id: UUID) -> Payment | None:
    return await session.get(Payment, payment_id)


async def list_payments(
    session: AsyncSession, email: str | None, status: str | None
) -> list[Payment]:
    statement = select(Payment)
    if email is not None:
        statement = statement.where(Payment.email == email)
    if status is not None:
        statement = statement.where(Payment.status == status)
    statement = statement.order_by(Payment.created_at, Payment.id)
    return list(await session.scalars(statement))


async def change_payment_status(
    session: AsyncSession, payment_id: UUID, target: PaymentStatus
) -> None:
    async with session.begin():
        payment = await session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        if payment is None:
            raise PaymentNotFound
        if not can_transition(PaymentStatus(payment.status), target):
            raise InvalidTransition
        payment.status = target.value
