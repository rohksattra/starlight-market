from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from core.constants import DONOR_COUPON_DISCOUNT_RATE
from services.economy import EconomyService


def _run(coro):
    return asyncio.run(coro)


def _service(*, fee_rate: float = 0.01) -> EconomyService:
    ctx = MagicMock()
    ctx.db_name = "test"
    ctx.economy.worker_fee_rate = fee_rate
    with (
        patch("services.economy.UserRepo"),
        patch("services.economy.ItemRepo"),
        patch("services.economy.OrderRepo"),
        patch("services.economy.StatisticRepo"),
        patch("services.economy.TransactionRepo"),
    ):
        service = EconomyService(ctx)
    service.users = AsyncMock()
    service.items = AsyncMock()
    service.orders = AsyncMock()
    service.statistics = AsyncMock()
    service.transactions = AsyncMock()
    return service


def test_quantity_must_be_positive() -> None:
    service = _service()
    try:
        service._validate_quantity(0)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Quantity must be > 0" in str(exc)


def test_worker_keep_rate_uses_tenant_fee() -> None:
    service = _service(fee_rate=0.01)
    assert service._worker_keep_rate() == 0.99
    service = _service(fee_rate=0.05)
    assert abs(service._worker_keep_rate() - 0.95) < 1e-9


def test_paid_worker_applies_fee_and_records_income() -> None:
    service = _service(fee_rate=0.01)
    service.items.get_by_id.return_value = {"item_name": "Iron Ore", "item_price": 100}

    result = _run(service.paid_worker(user_id="w1", item_id="i1", quantity=10))

    assert result["income"] == 990
    assert result["item_name"] == "Iron Ore"
    service.users.inc_worker_income.assert_awaited_once()
    service.statistics.inc_worker_income.assert_awaited_once_with(amount=990)


def test_paid_worker_unknown_item() -> None:
    service = _service()
    service.items.get_by_id.return_value = None
    try:
        _run(service.paid_worker(user_id="w1", item_id="missing", quantity=1))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Item not found" in str(exc)


def test_spent_customer_records_full_price() -> None:
    service = _service()
    service.items.get_by_id.return_value = {"item_name": "Iron Ore", "item_price": 50}

    result = _run(service.spent_customer(user_id="c1", item_id="i1", quantity=4))

    assert result["spent"] == 200
    service.users.inc_customer_spent.assert_awaited_once_with(user_id="c1", amount=200)
    service.items.inc_item_sold.assert_awaited_once_with(item_id="i1", qty=4)
    service.statistics.inc_customer_spent.assert_awaited_once_with(amount=200)


def test_donation_rejects_non_positive_gold() -> None:
    service = _service()
    try:
        _run(service.record_donation(user_id="u1", gold=0))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Gold must be > 0" in str(exc)


def test_coupon_discount_constant() -> None:
    assert DONOR_COUPON_DISCOUNT_RATE == 0.005
