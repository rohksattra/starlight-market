from __future__ import annotations

import pytest

from core.constants import DONOR_COUPON_DISCOUNT_RATE
from database.items import ItemRepo
from database.orders import OrderRepo
from database.statistics import StatisticRepo
from database.users import UserRepo
from services.economy import EconomyService
from services.order_claim import OrderClaimService
from tests.integration.mongo import run_mongo_test, sample_order

pytestmark = pytest.mark.integration


async def _insert_item(ctx, *, item_id: str = "item-1", price: int = 100) -> None:
    await ItemRepo(ctx.db_name).items.insert_one(
        {
            "item_id": item_id,
            "item_category": "ore",
            "item_name": "Iron Ore",
            "item_price": price,
            "item_sold": 0,
            "item_image": "",
            "item_emoji": "",
        }
    )


def test_paid_worker_persists_income() -> None:
    async def body(ctx) -> None:
        await _insert_item(ctx)
        economy = EconomyService(ctx)

        result = await economy.paid_worker(user_id="w1", item_id="item-1", quantity=10)

        assert result["income"] == 990
        user = await UserRepo(ctx.db_name).get_user("w1")
        assert user is not None
        assert int(user["total_worker_income"]) == 990
        assert int(user["total_worker_finished_item"]) == 10
        stats = await StatisticRepo(ctx.db_name).get_global()
        assert stats is not None
        assert int(stats["gold"]["total_worker_income"]) == 990

    run_mongo_test(body)


def test_worker_income_after_claim() -> None:
    async def body(ctx) -> None:
        await _insert_item(ctx)
        orders = OrderRepo(ctx.db_name)
        await orders.create_order(sample_order(item_quantity=10, item_price=100))
        await OrderClaimService(ctx).claim(order_id="ord-1", worker_id="w1", qty=10)

        result = await EconomyService(ctx).record_income(
            channel_id="ch-1",
            target="worker",
            user_id="w1",
            quantity=10,
        )

        assert result["finished"] is True
        user = await UserRepo(ctx.db_name).get_user("w1")
        assert user is not None
        assert int(user["total_worker_income"]) == 990
        stored = await orders.get_by_id("ord-1")
        assert stored is not None
        assert stored["order_status"] == "completed"
        assert int(stored["order_claims"]["order_completed"]) == 10

    run_mongo_test(body, replica=True)


def test_worker_cannot_complete_more_than_claimed() -> None:
    async def body(ctx) -> None:
        await _insert_item(ctx)
        await OrderRepo(ctx.db_name).create_order(sample_order(item_quantity=10))
        await OrderClaimService(ctx).claim(order_id="ord-1", worker_id="w1", qty=3)

        try:
            await EconomyService(ctx).record_income(
                channel_id="ch-1",
                target="worker",
                user_id="w1",
                quantity=4,
            )
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "Cannot complete more than claimed" in str(exc)

        user = await UserRepo(ctx.db_name).get_user("w1")
        assert user is None or int(user.get("total_worker_income") or 0) == 0

    run_mongo_test(body, replica=True)


def test_customer_income_after_worker_complete() -> None:
    async def body(ctx) -> None:
        await _insert_item(ctx)
        orders = OrderRepo(ctx.db_name)
        await orders.create_order(sample_order(item_quantity=10, item_price=100))
        await OrderClaimService(ctx).claim(order_id="ord-1", worker_id="w1", qty=10)
        economy = EconomyService(ctx)
        await economy.record_income(
            channel_id="ch-1",
            target="worker",
            user_id="w1",
            quantity=10,
        )

        result = await economy.record_income(
            channel_id="ch-1",
            target="customer",
            user_id="c1",
            quantity=10,
        )

        assert result["delivered"] is True
        customer = await UserRepo(ctx.db_name).get_user("c1")
        assert customer is not None
        assert int(customer["total_customer_spent"]) == 1000
        stored = await orders.get_by_id("ord-1")
        assert stored is not None
        assert stored["order_status"] == "delivered"
        item = await ItemRepo(ctx.db_name).get_by_id("item-1")
        assert item is not None
        assert int(item["item_sold"]) == 10

    run_mongo_test(body, replica=True)


def test_customer_income_applies_coupon_discount() -> None:
    async def body(ctx) -> None:
        await _insert_item(ctx)
        await OrderRepo(ctx.db_name).create_order(
            sample_order(item_quantity=10, item_price=100, coupon_applied=True)
        )
        await OrderClaimService(ctx).claim(order_id="ord-1", worker_id="w1", qty=10)
        economy = EconomyService(ctx)
        await economy.record_income(
            channel_id="ch-1",
            target="worker",
            user_id="w1",
            quantity=10,
        )

        await economy.record_income(
            channel_id="ch-1",
            target="customer",
            user_id="c1",
            quantity=10,
        )

        customer = await UserRepo(ctx.db_name).get_user("c1")
        assert customer is not None
        assert int(customer["total_customer_spent"]) == int(1000 * (1 - DONOR_COUPON_DISCOUNT_RATE))

    run_mongo_test(body, replica=True)
