from __future__ import annotations

from datetime import datetime
from typing import Any

from bson.int64 import Int64

from db.mongo import get_db
from app.domains.statistic_domain import GlobalStatistics


StatisticData = GlobalStatistics

_GLOBAL_ID = "global"


Session = Any


class StatisticRepository:
    def __init__(self) -> None:
        self.stats = get_db().statistics

    def _session_kw(self, session: Session | None) -> dict:
        return {} if session is None else {"session": session}

    async def ensure_global(self) -> None:
        await self.stats.update_one(
            {"_id": _GLOBAL_ID},
            {"$setOnInsert": {
                "_id": _GLOBAL_ID,
                "orders": {
                    "total_customer_order": Int64(0),
                    "total_finished_order": Int64(0),
                    "total_canceled_order": Int64(0),
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

    async def inc_customer_order(self, *, qty: int = 1, session: Session | None = None) -> None:
        await self.stats.update_one(
            {"_id": _GLOBAL_ID},
            {
                "$inc": {"orders.total_customer_order": Int64(qty)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
            **self._session_kw(session),
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

    async def inc_canceled_order(self, *, qty: int = 1) -> None:
        await self.stats.update_one(
            {"_id": _GLOBAL_ID},
            {
                "$inc": {"orders.total_canceled_order": Int64(qty)},
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
