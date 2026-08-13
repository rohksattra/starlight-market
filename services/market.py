"""Service for market: price panels, mstat, claimable, leaderboards."""
from __future__ import annotations

from typing import Any

from core.tenant import GameContext
from database.items import ItemRepo
from database.leaderboard import LeaderboardRepo
from database.orders import OrderRepo
from database.statistics import StatisticRepo
from models.enums import OrderStatus


class MarketService:
    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self.orders = OrderRepo(ctx.db_name)
        self.stats = StatisticRepo(ctx.db_name)
        self.leaderboards = LeaderboardRepo(ctx.db_name)
        self.items = ItemRepo(ctx.db_name)

    async def _inject_item_emoji(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return rows

        item_ids = {r.get("item_id") for r in rows if r.get("item_id")}
        db_items = await self.items.get_all()
        emoji_map = {
            i["item_id"]: i.get("item_emoji") or "🌟"
            for i in db_items
            if i.get("item_id") in item_ids
        }
        for row in rows:
            row["item_emoji"] = emoji_map.get(row.get("item_id")) or "🌟"
        return rows

    async def market_statistic(self) -> dict[str, Any]:
        active = await self.orders.count_by_statuses([OrderStatus.NEW, OrderStatus.CLAIMED])
        completed = await self.orders.count_by_status(OrderStatus.COMPLETED)

        stats = await self.stats.get_global()
        if not stats:
            raise ValueError("Statistic not initialized")

        orders = stats.get("orders") or {}
        gold = stats.get("gold") or {}
        if not orders or not gold:
            raise ValueError("Statistic data incomplete")

        top_items = await self.leaderboards.top_items(limit=5)
        top_items = await self._inject_item_emoji(top_items)

        return {
            "order": {
                "total": int(orders.get("total_customer_order", 0) or 0),
                "active": active,
                "completed": completed,
                "finished": int(orders.get("total_finished_order", 0) or 0),
                "canceled": int(orders.get("total_canceled_order", 0) or 0),
            },
            "gold": {
                "worker_income": int(gold.get("total_worker_income", 0) or 0),
                "customer_spent": int(gold.get("total_customer_spent", 0) or 0),
            },
            "leaderboard": {
                "workers": await self.leaderboards.top_workers(limit=5),
                "customers": await self.leaderboards.top_customers(limit=5),
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

    async def top_workers(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self.leaderboards.top_workers(limit=limit)

    async def top_customers(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self.leaderboards.top_customers(limit=limit)

    async def top_donors(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self.leaderboards.top_donors(limit=limit)

    async def top_items(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self.leaderboards.top_items(limit=limit)
        return await self._inject_item_emoji(rows)

    async def top_rated_workers(
        self,
        *,
        limit: int = 100,
        min_count: int = 1,
    ) -> list[dict[str, Any]]:
        return await self.leaderboards.top_rated_workers(limit=limit, min_count=min_count)
