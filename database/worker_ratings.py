"""Mongo queries for the worker_ratings collection."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


from database.connection import get_db


class WorkerRatingRepo:
    def __init__(self, db_name: str) -> None:
        self.worker_ratings = get_db(db_name).worker_ratings

    async def create_rating(self, rating: dict[str, Any]) -> None:
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

    async def get_by_transaction(self, transaction_id: str) -> Optional[dict[str, Any]]:
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
                },
                "$unset": {"expired_at": ""},
            },
        )
        return res.modified_count == 1

    async def top_since(
        self,
        *,
        since: datetime | None,
        limit: int = 100,
        min_count: int = 1,
    ) -> list[dict[str, Any]]:
        match: dict[str, Any] = {"rated": True, "rating": {"$ne": None}}
        if since is not None:
            match["rated_at"] = {"$gte": since}
        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": "$worker_id",
                    "total": {"$sum": "$rating"},
                    "count": {"$sum": 1},
                }
            },
            {"$match": {"count": {"$gte": min_count}}},
            {
                "$project": {
                    "avg": {"$divide": ["$total", "$count"]},
                    "count": 1,
                }
            },
            {"$sort": {"avg": -1, "count": -1}},
            {"$limit": limit},
        ]
        return [
            {
                "id": d["_id"],
                "avg": float(d.get("avg", 0)),
                "count": int(d.get("count", 0)),
            }
            async for d in self.worker_ratings.aggregate(pipeline)
        ]

    async def delete_older_than(self, cutoff: datetime) -> int:
        result = await self.worker_ratings.delete_many(
            {
                "$or": [
                    {"rated_at": {"$lt": cutoff}},
                    {"expired_at": {"$lt": cutoff}},
                ],
            }
        )
        return int(result.deleted_count)
