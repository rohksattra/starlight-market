from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from database.orders import OrderRepo
from services.order_claim import OrderClaimService
from services.tiers import DEFAULT_WORKER_LIMITS
from tests.integration.mongo import run_mongo_test, sample_order

pytestmark = pytest.mark.integration


def test_claim_persists_quantity() -> None:
    async def body(ctx) -> None:
        orders = OrderRepo(ctx.db_name)
        await orders.create_order(sample_order(item_quantity=10))
        service = OrderClaimService(ctx)

        updated = await service.claim(order_id="ord-1", worker_id="w1", qty=3)

        assert int(updated["worker_claims"]["w1"]) == 3
        assert int(updated["order_claims"]["order_claimed"]) == 3
        assert int(updated["order_claims"]["order_claimable"]) == 7
        stored = await orders.get_by_id("ord-1")
        assert stored is not None
        assert stored["order_status"] == "claimed"
        assert int(stored["worker_claims"]["w1"]) == 3

    run_mongo_test(body)


def test_claim_rejects_when_not_enough_claimable() -> None:
    async def body(ctx) -> None:
        orders = OrderRepo(ctx.db_name)
        await orders.create_order(sample_order(item_quantity=4))
        service = OrderClaimService(ctx)
        await service.claim(order_id="ord-1", worker_id="w1", qty=3)

        try:
            await service.claim(order_id="ord-1", worker_id="w2", qty=2)
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "Not enough claimable quantity" in str(exc)

        stored = await orders.get_by_id("ord-1")
        assert stored is not None
        assert int(stored["order_claims"]["order_claimable"]) == 1
        assert "w2" not in (stored.get("worker_claims") or {})

    run_mongo_test(body)


def test_concurrent_claims_do_not_over_allocate() -> None:
    async def body(ctx) -> None:
        orders = OrderRepo(ctx.db_name)
        await orders.create_order(sample_order(item_quantity=10))
        service = OrderClaimService(ctx)

        results = await asyncio.gather(
            service.claim(order_id="ord-1", worker_id="w1", qty=6),
            service.claim(order_id="ord-1", worker_id="w2", qty=6),
            return_exceptions=True,
        )
        successes = [item for item in results if not isinstance(item, BaseException)]
        failures = [item for item in results if isinstance(item, BaseException)]
        assert len(successes) == 1
        assert len(failures) == 1
        assert any("Not enough claimable quantity" in str(item) for item in failures)

        stored = await orders.get_by_id("ord-1")
        assert stored is not None
        claimed = int(stored["order_claims"]["order_claimed"])
        claimable = int(stored["order_claims"]["order_claimable"])
        assert claimed == 6
        assert claimable == 4
        assert claimed + claimable == 10

    run_mongo_test(body)


def test_unclaim_restores_new_order() -> None:
    async def body(ctx) -> None:
        orders = OrderRepo(ctx.db_name)
        await orders.create_order(sample_order(item_quantity=8))
        service = OrderClaimService(ctx)
        await service.claim(order_id="ord-1", worker_id="w1", qty=8)

        updated = await service.unclaim(order_id="ord-1", worker_id="w1", qty=8)

        assert updated["order_status"] == "new"
        assert int(updated["order_claims"]["order_claimable"]) == 8
        stored = await orders.get_by_id("ord-1")
        assert stored is not None
        assert stored["order_status"] == "new"
        assert "w1" not in (stored.get("worker_claims") or {})

    run_mongo_test(body)


def test_over_capacity_claim_rolls_back() -> None:
    async def body(ctx) -> None:
        qty = DEFAULT_WORKER_LIMITS.claim_capacity + 1
        orders = OrderRepo(ctx.db_name)
        await orders.create_order(sample_order(item_quantity=qty))
        service = OrderClaimService(ctx)

        with patch.object(service.tier_limits, "validate_worker_claim", new_callable=AsyncMock):
            try:
                await service.claim(order_id="ord-1", worker_id="w1", qty=qty)
                raise AssertionError("expected ValueError")
            except ValueError as exc:
                assert "Claim capacity" in str(exc)

        stored = await orders.get_by_id("ord-1")
        assert stored is not None
        assert int(stored["order_claims"]["order_claimable"]) == qty
        assert int((stored.get("worker_claims") or {}).get("w1") or 0) == 0

    run_mongo_test(body)
