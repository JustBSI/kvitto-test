"""Public request and response schemas, independent of database tables."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.business import ALLOWED_MONTHS, PaymentMethod, PaymentStatus


class TariffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    price: int


class PaymentCreate(BaseModel):
    # Tariff IDs use PostgreSQL INTEGER (signed 32-bit), not Python's unbounded int.
    tariff_id: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    email: EmailStr
    method: PaymentMethod
    installment_months: Annotated[int, Field(strict=True)] | None = None
    promo_code: str | None = None

    @field_validator("promo_code")
    @classmethod
    def validate_promo_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.upper() != "KVITTO10":
            raise ValueError("Unknown promo code")
        return value.upper()

    @model_validator(mode="after")
    def validate_installment(self) -> Self:
        if self.method == PaymentMethod.INSTALLMENT:
            if self.installment_months not in ALLOWED_MONTHS:
                raise ValueError("Installment requires 3, 6 or 12 months")
        elif self.installment_months is not None:
            raise ValueError("Card and sbp must not specify installment_months")
        return self


class PaymentResponse(BaseModel):
    id: UUID
    status: PaymentStatus
    tariff_id: int
    amount: int
    discount: int
    method: PaymentMethod
    installment_months: int | None
    schedule: list[int] | None
    email: EmailStr
    created_at: datetime


class BankWebhook(BaseModel):
    payment_id: UUID
    status: Literal["pending", "succeeded", "failed", "refunded"]


class WebhookResult(BaseModel):
    result: Literal["ok"] = "ok"
