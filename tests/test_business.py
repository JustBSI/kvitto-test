import pytest

from app.business import (
    PaymentStatus,
    calculate_amount,
    can_transition,
    installment_schedule,
)


@pytest.mark.parametrize("price", [990000, 1990000, 2990000])
@pytest.mark.parametrize("promo", [None, "KVITTO10", "kvitto10", "Kvitto10"])
def test_amount_and_discount(price: int, promo: str | None) -> None:
    amount, discount = calculate_amount(price, promo)
    expected_discount = 0 if promo is None else price // 10
    assert discount == expected_discount
    assert amount == price - expected_discount
    assert type(amount) is int
    assert type(discount) is int


def test_unknown_promo_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown promo"):
        calculate_amount(990000, "other")


@pytest.mark.parametrize("months", [3, 6, 12])
def test_schedule_invariants(months: int) -> None:
    for amount in [*range(101), 990000, 1990000, 2990000, 1791000]:
        schedule = installment_schedule(amount, months)
        assert len(schedule) == months
        assert sum(schedule) == amount
        assert all(type(payment) is int for payment in schedule)
        assert max(schedule) - min(schedule) <= 1
        assert schedule == sorted(schedule, reverse=True)
    if months == 3:
        assert installment_schedule(1990000, months) == [663334, 663333, 663333]


@pytest.mark.parametrize("months", [0, 1, 4, 24])
def test_invalid_schedule_term(months: int) -> None:
    with pytest.raises(ValueError, match="term"):
        installment_schedule(100, months)


def test_negative_schedule_amount() -> None:
    with pytest.raises(ValueError, match="negative"):
        installment_schedule(-1, 3)


@pytest.mark.parametrize("current", list(PaymentStatus))
@pytest.mark.parametrize("target", list(PaymentStatus))
def test_all_status_transitions(current: PaymentStatus, target: PaymentStatus) -> None:
    allowed = {
        (PaymentStatus.PENDING, PaymentStatus.SUCCEEDED),
        (PaymentStatus.PENDING, PaymentStatus.FAILED),
        (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED),
    }
    assert can_transition(current, target) is ((current, target) in allowed)
