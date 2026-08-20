"""Service for market: price panels, mstat, claimable, leaderboards."""
from __future__ import annotations

from typing import Any

from core.period import StatPeriod, period_cutoff
from core.tenant import GameContext
from database.donations import DonationRepo
from database.items import ItemRepo
from database.leaderboard import LeaderboardRepo
from database.orders import OrderRepo
from database.statistics import StatisticRepo
from database.transaction_docs import TransactionRepo
from database.worker_ratings import WorkerRatingRepo
from models.enums import OrderStatus, ServerRole


class MarketService:
    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self.orders = OrderRepo(ctx.db_name)
        self.stats = StatisticRepo(ctx.db_name)
        self.leaderboards = LeaderboardRepo(ctx.db_name)
        self.items = ItemRepo(ctx.db_name)
        self.transactions = TransactionRepo(ctx.db_name)
        self.donations = DonationRepo(ctx.db_name)
        self.ratings = WorkerRatingRepo(ctx.db_name)

    async def _inject_item_emoji(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return rows

        item_ids = {r.get("item_id") for r in rows if r.get("item_id")}
        db_items = await self.items.get_all()
        by_id = {
            i["item_id"]: i
            for i in db_items
            if i.get("item_id") in item_ids
        }
        for row in rows:
            item = by_id.get(row.get("item_id"))
            if item is not None:
                row.setdefault("name", item.get("item_name") or "Unknown")
                row["item_emoji"] = item.get("item_emoji") or "🌟"
            else:
                row.setdefault("name", "Unknown")
                row["item_emoji"] = row.get("item_emoji") or "🌟"
        return rows

    def _commission(self, customer_spent: int) -> int:
        return int(customer_spent * float(self.ctx.economy.worker_fee_rate))

    @staticmethod
    def _avg_order_size(*, items_sold: int, created: int) -> int:
        if created <= 0:
            return 0
        return int((items_sold / created) + 0.5)

    async def market_statistic(self, *, period: StatPeriod = "all") -> dict[str, Any]:
        active = await self.orders.count_by_statuses([OrderStatus.NEW, OrderStatus.CLAIMED])
        completed = await self.orders.count_by_status(OrderStatus.COMPLETED)
        cutoff = period_cutoff(period)

        if cutoff is None:
            stats = await self.stats.get_global()
            if not stats:
                raise ValueError("Statistic not initialized")

            orders = stats.get("orders") or {}
            gold = stats.get("gold") or {}
            if not orders or not gold:
                raise ValueError("Statistic data incomplete")

            created = int(orders.get("total_customer_order", 0) or 0)
            finished = int(orders.get("total_finished_order", 0) or 0)
            canceled = int(orders.get("total_canceled_order", 0) or 0)
            worker_income = int(gold.get("total_worker_income", 0) or 0)
            customer_spent = int(gold.get("total_customer_spent", 0) or 0)
            items_sold = await self.items.sum_item_sold()
            top_workers = await self.leaderboards.top_workers(limit=5)
            top_customers = await self.leaderboards.top_customers(limit=5)
            top_items = await self.leaderboards.top_items(limit=5)
        else:
            created = await self.orders.count_created_since(cutoff)
            finished = await self.orders.count_by_status_updated_since(
                OrderStatus.CLOSED, cutoff
            )
            canceled = await self.orders.count_by_status_updated_since(
                OrderStatus.CANCELED, cutoff
            )
            worker_income = await self.transactions.sum_total_price(
                role=ServerRole.WORKER, since=cutoff
            )
            customer_spent = await self.transactions.sum_total_price(
                role=ServerRole.CUSTOMER, since=cutoff
            )
            items_sold = await self.transactions.sum_item_quantity(
                role=ServerRole.CUSTOMER, since=cutoff
            )
            top_workers = await self.transactions.top_users(
                role=ServerRole.WORKER, since=cutoff, limit=5
            )
            top_customers = await self.transactions.top_users(
                role=ServerRole.CUSTOMER, since=cutoff, limit=5
            )
            top_items = await self.transactions.top_items(since=cutoff, limit=5)

        top_items = await self._inject_item_emoji(top_items)

        return {
            "order": {
                "created": created,
                "active": active,
                "completed": completed,
                "finished": finished,
                "canceled": canceled,
            },
            "gold": {
                "worker_income": worker_income,
                "customer_spent": customer_spent,
                "commission": self._commission(customer_spent),
                "commission_rate": float(self.ctx.economy.worker_fee_rate),
                "items_sold": items_sold,
                "avg_order_size": self._avg_order_size(
                    items_sold=items_sold, created=created
                ),
            },
            "leaderboard": {
                "workers": top_workers,
                "customers": top_customers,
                "items": top_items,
            },
        }

    async def list_claimable(self) -> list[dict[str, Any]]:
        orders = await self.orders.get_claimable_orders()
        orders.sort(key=lambda o: int(o.get("order_number", 0) or 0))

        rows = [
            {
                "order_number": o.get("order_number", 0),
                "item_id": o.get("item_id"),
                "item_name": o.get("item_name", "Unknown"),
                "value": int(o.get("order_claims", {}).get("order_claimable", 0) or 0),
                "channel_id": o.get("channel_id"),
            }
            for o in orders
        ]
        return await self._inject_item_emoji(rows)

    async def top_workers(
        self, *, limit: int = 100, period: StatPeriod = "all"
    ) -> list[dict[str, Any]]:
        cutoff = period_cutoff(period)
        if cutoff is None:
            return await self.leaderboards.top_workers(limit=limit)
        return await self.transactions.top_users(
            role=ServerRole.WORKER, since=cutoff, limit=limit
        )

    async def top_customers(
        self, *, limit: int = 100, period: StatPeriod = "all"
    ) -> list[dict[str, Any]]:
        cutoff = period_cutoff(period)
        if cutoff is None:
            return await self.leaderboards.top_customers(limit=limit)
        return await self.transactions.top_users(
            role=ServerRole.CUSTOMER, since=cutoff, limit=limit
        )

    async def top_donors(
        self, *, limit: int = 100, period: StatPeriod = "all"
    ) -> list[dict[str, Any]]:
        cutoff = period_cutoff(period)
        if cutoff is None:
            return await self.leaderboards.top_donors(limit=limit)
        return await self.donations.top_since(since=cutoff, limit=limit)

    async def top_items(
        self, *, limit: int = 100, period: StatPeriod = "all"
    ) -> list[dict[str, Any]]:
        cutoff = period_cutoff(period)
        if cutoff is None:
            rows = await self.leaderboards.top_items(limit=limit)
        else:
            rows = await self.transactions.top_items(since=cutoff, limit=limit)
        return await self._inject_item_emoji(rows)

    async def top_rated_workers(
        self,
        *,
        limit: int = 100,
        min_count: int = 1,
        period: StatPeriod = "all",
    ) -> list[dict[str, Any]]:
        cutoff = period_cutoff(period)
        if cutoff is None:
            return await self.leaderboards.top_rated_workers(
                limit=limit, min_count=min_count
            )
        return await self.ratings.top_since(
            since=cutoff, limit=limit, min_count=min_count
        )
