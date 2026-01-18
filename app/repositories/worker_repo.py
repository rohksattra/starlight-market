# app/repositories/worker_repo.py
from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime
from bson.int64 import Int64

from db.mongo import get_db


WorkerData = Dict[str, Any]


class WorkerRepository:
    def __init__(self) -> None:
        self.workers = get_db().workers

    async def get_worker(self, worker_id: str) -> Optional[WorkerData]:
        return await self.workers.find_one({"worker_id": worker_id}, {"_id": 0})

    async def ensure_worker(self, worker_id: str) -> None:
        await self.workers.update_one(
            {"worker_id": worker_id},
            {
                "$setOnInsert": {
                    "worker_id": worker_id,
                    "total_worker_finished_item": Int64(0),
                    "total_worker_income": Int64(0),
                    "count_worker_rating": Int64(0),
                    "total_worker_star": Int64(0),
                    "updated_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )

    async def inc_worker_income(self, *, worker_id: str, finished_item_inc: int = 0, income_inc: int = 0) -> None:
        await self.workers.update_one(
            {"worker_id": worker_id},
            {
                "$inc": {
                    "total_worker_finished_item": Int64(finished_item_inc),
                    "total_worker_income": Int64(income_inc),
                },
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def inc_worker_rating(self, *, worker_id: str, rating: int) -> None:
        await self.workers.update_one(
            {"worker_id": worker_id},
            {
                "$inc": {
                    "count_worker_rating": Int64(1),
                    "total_worker_star": Int64(rating),
                },
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def get_rank_worker(self, worker_id: str) -> int | None:
        doc = await self.workers.find_one(
            {"worker_id": worker_id},
            {"total_worker_income": 1},
        )
        if not doc:
            return None
        income = int(doc.get("total_worker_income", 0))
        higher = await self.workers.count_documents(
            {"total_worker_income": {"$gt": income}}
        )
        return higher + 1
