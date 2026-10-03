"""HTTP handlers translate validated requests into business operations."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import EmailStr, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import services
from app.business import PaymentStatus, installment_schedule
from app.database import get_session
from app.models import Payment, Tariff
from app.schemas import (
    BankWebhook,
    PaymentCreate,
    PaymentResponse,
    TariffResponse,
    WebhookResult,
)
from app.security import valid_signature

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


def payment_response(payment: Payment) -> PaymentResponse:
    schedule = None
    if payment.installment_months is not None:
        schedule = installment_schedule(payment.amount, payment.installment_months)
    return PaymentResponse(
        id=payment.id,
        status=payment.status,
        tariff_id=payment.tariff_id,
        amount=payment.amount,
        discount=payment.discount,
        method=payment.method,
        installment_months=payment.installment_months,
        schedule=schedule,
        email=payment.email,
        created_at=payment.created_at,
    )


@router.get("/tariffs", response_model=list[TariffResponse])
async def list_tariffs(session: Session) -> list[Tariff]:
    result = await session.scalars(select(Tariff).order_by(Tariff.price, Tariff.id))
    return list(result)


@router.post(
    "/payments",
    response_model=PaymentResponse,
    status_code=201,
    responses={200: {"model": PaymentResponse}, 404: {"description": "Unknown tariff"}},
)
async def post_payment(
    data: PaymentCreate,
    response: Response,
    session: Session,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
) -> PaymentResponse:
    try:
        payment, created = await services.create_payment(session, data, idempotency_key)
    except services.TariffNotFound:
        raise HTTPException(status_code=404, detail="tariff_not_found") from None
    response.status_code = 201 if created else 200
    return payment_response(payment)


@router.get("/payments", response_model=list[PaymentResponse])
async def get_payments(
    session: Session,
    email: EmailStr | None = None,
    status: PaymentStatus | None = None,
) -> list[PaymentResponse]:
    payments = await services.list_payments(session, email, status)
    return [payment_response(payment) for payment in payments]


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentResponse,
    responses={404: {"description": "Payment not found"}},
)
async def get_payment(payment_id: UUID, session: Session) -> PaymentResponse:
    payment = await services.get_payment(session, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment_not_found")
    return payment_response(payment)


@router.post(
    "/webhooks/bank",
    response_model=WebhookResult,
    responses={
        401: {"description": "Missing or invalid signature"},
        404: {"description": "Payment not found"},
        409: {"description": "Invalid status transition"},
        422: {"description": "Invalid webhook body"},
    },
    openapi_extra={
        "parameters": [
            {
                "name": "X-Signature",
                "in": "header",
                "required": True,
                "schema": {"type": "string"},
                "description": "HMAC-SHA256 of the raw request body",
            }
        ],
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": BankWebhook.model_json_schema()}
            },
        },
    },
)
async def bank_webhook(
    request: Request,
    session: Session,
) -> WebhookResult | JSONResponse:
    raw_body = await request.body()
    # Manual extraction preserves 401 for a missing header instead of FastAPI's 422.
    signature = request.headers.get("X-Signature")
    secret = request.app.state.settings.webhook_secret.get_secret_value()
    if not valid_signature(raw_body, signature, secret):
        raise HTTPException(status_code=401, detail="invalid_signature")

    # Parse only after authentication, including for malformed JSON. The explicit
    # requestBody above keeps this manually parsed endpoint documented in OpenAPI.
    try:
        data = BankWebhook.model_validate_json(raw_body)
    except ValidationError as error:
        errors = error.errors(include_input=False)
        for item in errors:
            item["loc"] = ("body", *item["loc"])
        raise RequestValidationError(errors) from None

    try:
        await services.change_payment_status(
            session, data.payment_id, PaymentStatus(data.status)
        )
    except services.PaymentNotFound:
        raise HTTPException(status_code=404, detail="payment_not_found") from None
    except services.InvalidTransition:
        return JSONResponse(status_code=409, content={"error": "invalid_transition"})
    return WebhookResult()
