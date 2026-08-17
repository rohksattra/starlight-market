from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.tier_limits import TierLimitsService
from services.tiers import DEFAULT_CUSTOMER_LIMITS, DEFAULT_WORKER_LIMITS


def _run(coro):
    return asyncio.run(coro)


def _service() -> tuple[TierLimitsService, AsyncMock, AsyncMock]:
    ctx = MagicMock()
    ctx.db_name = "test"
    with (
        patch("services.tier_limits.UserRepo") as users_cls,
        patch("services.tier_limits.OrderRepo") as orders_cls,
    ):
        users = AsyncMock()
        orders = AsyncMock()
        users_cls.return_value = users
        orders_cls.return_value = orders
        service = TierLimitsService(ctx)
    service.users = users
    service.orders = orders
    return service, users, orders


def test_customer_order_rejected_at_active_limit() -> None:
    service, users, orders = _service()
    users.get_user.return_value = {"total_customer_spent": 0}
    orders.count_active_by_customer.return_value = DEFAULT_CUSTOMER_LIMITS.max_active_orders

    try:
        _run(service.validate_customer_order(customer_id="c1", quantity=1))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Active order limit reached" in str(exc)


def test_customer_order_rejected_over_capacity() -> None:
    service, users, orders = _service()
    users.get_user.return_value = {"total_customer_spent": 0}
    orders.count_active_by_customer.return_value = 0
    orders.sum_active_quantity_by_customer.return_value = DEFAULT_CUSTOMER_LIMITS.order_capacity - 10

    try:
        _run(service.validate_customer_order(customer_id="c1", quantity=20))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Order capacity limit reached" in str(exc)


def test_customer_order_allowed_under_limits() -> None:
    service, users, orders = _service()
    users.get_user.return_value = {"total_customer_spent": 0}
    orders.count_active_by_customer.return_value = 0
    orders.sum_active_quantity_by_customer.return_value = 0
    _run(service.validate_customer_order(customer_id="c1", quantity=100))


def test_worker_claim_rejected_when_order_missing() -> None:
    service, _users, orders = _service()
    orders.get_by_id.return_value = None
    try:
        _run(service.validate_worker_claim(worker_id="w1", order_id="missing", quantity=1))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Order not found" in str(exc)


def test_worker_claim_rejected_at_order_count_limit() -> None:
    service, users, orders = _service()
    orders.get_by_id.return_value = {"worker_claims": {}}
    users.get_user.return_value = {"total_worker_income": 0}
    orders.count_active_by_worker.return_value = DEFAULT_WORKER_LIMITS.max_claim_orders

    try:
        _run(service.validate_worker_claim(worker_id="w1", order_id="o1", quantity=1))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Claim order limit reached" in str(exc)


def test_worker_already_on_order_skips_count_limit() -> None:
    service, users, orders = _service()
    orders.get_by_id.return_value = {"worker_claims": {"w1": 5}}
    users.get_user.return_value = {"total_worker_income": 0}
    orders.sum_active_claim_quantity_by_worker.return_value = 5

    _run(service.validate_worker_claim(worker_id="w1", order_id="o1", quantity=1))
    orders.count_active_by_worker.assert_not_called()
