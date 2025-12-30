# app/repositories/worker_rating_repo.py
from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime

from db.mongo import get_db


WorkerRatingData = Dict[str, Any]


class WorkerRatingRepository:
    def __init__(self) -> None:
        self.worker_ratings = get_db().worker_ratings

    async def create_rating(self, rating: WorkerRatingData) -> None:
        await self.worker_ratings.update_one(
            {"transaction_id": rating["transaction_id"]},
            {
                "$setOnInsert": {
                    "worker_rating_id": rating["worker_rating_id"],
                    "transaction_id": rating["transaction_id"],
                    "customer_id": rating["customer_id"],
                    "worker_id": rating["worker_id"],
                    "rating": None,
                    "rated": False,
                    "created_at": rating["created_at"],
                    "expired_at": rating["expired_at"],
                    "rated_at": None,
                }
            },
            upsert=True,
        )

    async def get_by_transaction(self, transaction_id: str) -> Optional[WorkerRatingData]:
        return await self.worker_ratings.find_one(
            {"transaction_id": transaction_id},
            {"_id": 0},
        )

    async def rating_submit(self, *, transaction_id: str, rating: int, rated_at: datetime) -> bool:
        res = await self.worker_ratings.update_one(
            {
                "transaction_id": transaction_id,
                "rated": False,
                "expired_at": {"$gte": rated_at},
            },
            {
                "$set": {
                    "rating": rating,
                    "rated": True,
                    "rated_at": rated_at,
                }
            },
        )
        return res.modified_count == 1

    async def mark_expired(self, *, now: datetime) -> int:
        res = await self.worker_ratings.update_many(
            {
                "rated": False,
                "expired_at": {"$lt": now},
            },
            {
                "$set": {"rated": False}
            },
        )
        return int(res.modified_count)
