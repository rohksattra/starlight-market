# app/services/statistic_service.py
from __future__ import annotations

from typing import Any, Dict, List

from app.domains.enums.order_status_enum import OrderStatus
from app.repositories.leaderboard_repo import LeaderboardRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.statistic_repo import StatisticRepository
from app.repositories.item_repo import ItemRepository


class StatisticService:
    def __init__(self) -> None:
        self.leaderboards = LeaderboardRepository()
        self.orders = OrderRepository()
        self.statictics = StatisticRepository()
        self.items = ItemRepository()

    async def _inject_item_emoji(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not rows:
            return rows

        item_ids = {r.get("item_id") for r in rows if r.get("item_id")}
        db_items = await self.items.get_all()

        emoji_map = {
            i["item_id"]: i.get("item_emoji", "🌟")
            for i in db_items
            if i["item_id"] in item_ids
        }

        for r in rows:
            r["item_emoji"] = emoji_map.get(r.get("item_id"), "🌟")

        return rows

    async def market_statistic(self) -> Dict[str, Any]:
        active = await self.orders.count_by_statuses([OrderStatus.NEW, OrderStatus.CLAIMED])
        completed = await self.orders.count_by_status(OrderStatus.COMPLETED)

        stats = await self.statictics.get_global()
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
                "total": orders.get("total_customer_order", 0),
                "active": active,
                "completed": completed,
                "finished": orders.get("total_finished_order", 0),
                "canceled": orders.get("total_canceled_order", 0),
            },
            "gold": {
                "worker_income": gold.get("total_worker_income", 0),
                "customer_spent": gold.get("total_customer_spent", 0),
            },
            "leaderboard": {
                "workers": await self.leaderboards.top_workers(limit=5),
                "customers": await self.leaderboards.top_customers(limit=5),
                "items": top_items,
            },
        }