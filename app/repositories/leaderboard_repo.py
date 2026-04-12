# app/repositories/leaderboard_repo.py
from __future__ import annotations

from typing import Any, Dict, List

from db.mongo import get_db


LeaderboardRow = Dict[str, Any]


class LeaderboardRepository:
    def __init__(self) -> None:
        db = get_db()
        self.workers = db.workers
        self.customers = db.customers
        self.items = db.items

    async def top_workers(self, *, limit: int = 100) -> List[LeaderboardRow]:
        cursor = (
            self.workers.find(
                {"total_worker_income": {"$gt": 0}},
                {"_id": 0, "worker_id": 1, "total_worker_income": 1},
            )
            .sort("total_worker_income", -1)
            .limit(limit)
        )
        return [
            {"id": d["worker_id"], "value": int(d["total_worker_income"])}
            async for d in cursor
        ]

    async def top_customers(self, *, limit: int = 100) -> List[LeaderboardRow]:
        cursor = (
            self.customers.find(
                {"total_customer_spent": {"$gt": 0}},
                {"_id": 0, "customer_id": 1, "total_customer_spent": 1},
            )
            .sort("total_customer_spent", -1)
            .limit(limit)
        )
        return [
            {"id": d["customer_id"], "value": int(d["total_customer_spent"])}
            async for d in cursor
        ]

    async def top_items(self, *, limit: int = 100) -> List[LeaderboardRow]:
        cursor = (
            self.items.find(
                {"item_sold": {"$gt": 0}},
                {"_id": 0, "item_name": 1, "item_sold": 1, "item_emoji": 1},
            )
            .sort("item_sold", -1)
            .limit(limit)
        )
        return [
            {"name": d["item_name"], "value": int(d["item_sold"]), "item_emoji": d.get("item_emoji", "")}
            async for d in cursor
        ]
