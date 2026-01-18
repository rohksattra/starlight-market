# app/repositories/statistic_repo.py
from __future__ import annotations

from typing import Any, Dict
from datetime import datetime
from bson.int64 import Int64

from db.mongo import get_db


StatisticData = Dict[str, Any]

_GLOBAL_ID = "global"


class StatisticRepository:
    def __init__(self) -> None:
        self.stats = get_db().statistics

    async def ensure_global(self) -> None:
        await self.stats.update_one(
            {"_id": _GLOBAL_ID},
            {"$setOnInsert": {
                "_id": _GLOBAL_ID,
                "orders": {
                    "total_customer_order": Int64(0),
                    "total_finished_order": Int64(0),
                    "total_cancelled_order": Int64(0),
                },
                "gold": {
                    "total_worker_income": Int64(0),
                    "total_customer_spent": Int64(0),
                },
                "updated_at": datetime.utcnow(),
            }},
            upsert=True,
        )

    async def get_global(self) -> StatisticData | None:
        return await self.stats.find_one({"_id": _GLOBAL_ID}, {"_id": 0})

    async def inc_customer_order(self, *, qty: int = 1) -> None:
        await self.stats.update_one(
            {"_id": _GLOBAL_ID},
            {
                "$inc": {"orders.total_customer_order": Int64(qty)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def inc_finished_order(self, *, qty: int = 1) -> None:
        await self.stats.update_one(
            {"_id": _GLOBAL_ID},
            {
                "$inc": {"orders.total_finished_order": Int64(qty)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def inc_cancelled_order(self, *, qty: int = 1) -> None:
        await self.stats.update_one(
            {"_id": _GLOBAL_ID},
            {
                "$inc": {"orders.total_cancelled_order": Int64(qty)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def inc_worker_income(self, *, amount: int) -> None:
        await self.stats.update_one(
            {"_id": _GLOBAL_ID},
            {
                "$inc": {"gold.total_worker_income": Int64(amount)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def inc_customer_spent(self, *, amount: int) -> None:
        await self.stats.update_one(
            {"_id": _GLOBAL_ID},
            {
                "$inc": {"gold.total_customer_spent": Int64(amount)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )
