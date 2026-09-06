"""Mongo queries for dated donation events."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from bson.int64 import Int64

from core.time import utc_now
from database.connection import get_db

Session = Any


class DonationRepo:
    def __init__(self, db_name: str) -> None:
        self.donations = get_db(db_name).donations

    def _session_kw(self, session: Session | None) -> dict:
        return {} if session is None else {"session": session}

    async def create(
        self,
        *,
        user_id: str,
        gold: int,
        session: Session | None = None,
    ) -> None:
        await self.donations.insert_one(
            {
                "donation_id": str(uuid4()),
                "user_id": user_id,
                "gold": Int64(gold),
                "created_at": utc_now(),
            },
            **self._session_kw(session),
        )

    async def top_since(self, *, since: datetime | None, limit: int = 100) -> list[dict[str, Any]]:
        match: dict[str, Any] = {"gold": {"$gt": 0}}
        if since is not None:
            match["created_at"] = {"$gte": since}
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$user_id", "value": {"$sum": "$gold"}}},
            {"$match": {"value": {"$gt": 0}}},
            {"$sort": {"value": -1}},
            {"$limit": limit},
        ]
        return [
            {"id": d["_id"], "value": int(d["value"])}
            async for d in self.donations.aggregate(pipeline)
        ]

    async def delete_created_before(self, cutoff: datetime) -> int:
        result = await self.donations.delete_many({"created_at": {"$lt": cutoff}})
        return int(result.deleted_count)
