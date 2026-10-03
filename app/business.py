"""Pure business rules: no HTTP, database access, or floating-point money."""

from enum import StrEnum


class PaymentMethod(StrEnum):
    CARD = "card"
    SBP = "sbp"
    INSTALLMENT = "installment"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


ALLOWED_MONTHS = (3, 6, 12)
ALLOWED_TRANSITIONS = {
    PaymentStatus.PENDING: {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED},
    PaymentStatus.SUCCEEDED: {PaymentStatus.REFUNDED},
    PaymentStatus.FAILED: set(),
    PaymentStatus.REFUNDED: set(),
}


def calculate_amount(price: int, promo_code: str | None) -> tuple[int, int]:
    """Return (amount, discount). Validate the promo even outside the HTTP layer."""
    if promo_code is None:
        discount = 0
    elif promo_code.upper() == "KVITTO10":
        discount = price * 10 // 100
    else:
        raise ValueError("Unknown promo code")
    return price - discount, discount


def installment_schedule(amount: int, months: int) -> list[int]:
    if months not in ALLOWED_MONTHS:
        raise ValueError("Installment term must be 3, 6 or 12 months")
    if amount < 0:
        raise ValueError("Amount must not be negative")
    base, remainder = divmod(amount, months)
    return [base + (1 if index < remainder else 0) for index in range(months)]


def can_transition(current: PaymentStatus, target: PaymentStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]
