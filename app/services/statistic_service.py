# app/services/statistic_service.py
from __future__ import annotations

from typing import Any, Dict

from app.domains.enums.order_status_enum import OrderStatus
from app.repositories.leaderboard_repo import LeaderboardRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.statistic_repo import StatisticRepository


class StatisticService:
    def __init__(self) -> None:
        self.leaderboards = LeaderboardRepository()
        self.orders = OrderRepository()
        self.statictics = StatisticRepository()

    async def market_statistic(self) -> Dict[str, Any]:
        active = await self.orders.count_by_statuses([OrderStatus.NEW, OrderStatus.CLAIMED])
        completed = await self.orders.count_by_status(OrderStatus.COMPLETED)
        stats = await self.statictics.get_global()
        if not stats:
            raise ValueError("Statistic not initialized")

        orders = stats["orders"]
        gold = stats["gold"]

        return {
            "order": {
                "total": orders["total_customer_order"],
                "active": active,
                "completed": completed,
                "finished": orders["total_finished_order"],
                "cancelled": orders["total_cancelled_order"],
            },
            "gold": {
                "worker_income": gold["total_worker_income"],
                "customer_spent": gold["total_customer_spent"],
            },
            "leaderboard": {
                "workers": await self.leaderboards.top_workers(limit=5),
                "customers": await self.leaderboards.top_customers(limit=5),
                "items": await self.leaderboards.top_items(limit=5),
            },
        }
