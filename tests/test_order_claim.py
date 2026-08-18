from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.order_claim import OrderClaimService


def _run(coro):
    return asyncio.run(coro)


def _service() -> tuple[OrderClaimService, AsyncMock, AsyncMock]:
    ctx = MagicMock()
    ctx.db_name = "test"
    with (
        patch("services.order_claim.OrderRepo") as repo_cls,
        patch("services.order_claim.TierLimitsService") as tier_cls,
    ):
        repo = AsyncMock()
        tier = AsyncMock()
        repo_cls.return_value = repo
        tier_cls.return_value = tier
        service = OrderClaimService(ctx)
    service.orders = repo
    service.tier_limits = tier
    return service, repo, tier


def test_claim_rejects_non_positive_quantity() -> None:
    service, repo, tier = _service()
    try:
        _run(service.claim(order_id="o1", worker_id="w1", qty=0))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "must be > 0" in str(exc)
    repo.inc_claim.assert_not_called()
    tier.validate_worker_claim.assert_not_called()


def test_claim_checks_tier_then_increments() -> None:
    service, repo, tier = _service()
    updated = {"order_id": "o1", "item_quantity": 10, "order_claims": {"order_claimable": 5}}
    repo.inc_claim.return_value = updated

    result = _run(service.claim(order_id="o1", worker_id="w1", qty=3))

    assert result is updated
    tier.validate_worker_claim.assert_awaited_once_with(
        worker_id="w1",
        order_id="o1",
        quantity=3,
    )
    repo.inc_claim.assert_awaited_once_with(order_id="o1", worker_id="w1", qty=3)


def test_claim_raises_when_not_enough_claimable() -> None:
    service, repo, _tier = _service()
    repo.inc_claim.return_value = None
    try:
        _run(service.claim(order_id="o1", worker_id="w1", qty=4))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Not enough claimable quantity" in str(exc)


def test_unclaim_clears_worker_and_resets_new_status() -> None:
    service, repo, _tier = _service()
    repo.inc_unclaim.return_value = {
        "order_id": "o1",
        "item_quantity": 10,
        "order_status": "claimed",
        "worker_claims": {"w1": 0},
        "order_claims": {"order_claimable": 10},
    }
    repo.update_fields.return_value = None

    result = _run(service.unclaim(order_id="o1", worker_id="w1", qty=2))

    repo.inc_unclaim.assert_awaited_once_with(order_id="o1", worker_id="w1", qty=2)
    repo.unset_worker_claim.assert_awaited_once_with(order_id="o1", worker_id="w1")
    repo.update_fields.assert_awaited_once()
    assert result["order_status"] == "new"


def test_force_claim_uses_same_tier_check() -> None:
    service, repo, tier = _service()
    repo.inc_claim.return_value = {"order_id": "o1"}
    _run(service.force_claim(order_id="o1", worker_id="w1", qty=1))
    tier.validate_worker_claim.assert_awaited_once()
