"""Mongo queries for CoA game worlds (boost reminder state)."""
from __future__ import annotations

from typing import Any

from database.connection import get_db

WorldDoc = dict[str, Any]


class WorldRepo:
    def __init__(self, db_name: str) -> None:
        self.worlds = get_db(db_name).worlds

    async def get_all(self, *, limit: int = 500) -> list[WorldDoc]:
        return await self.worlds.find({}, {"_id": 0}).limit(limit).to_list(length=limit)

    async def upsert_many(self, docs: list[WorldDoc]) -> None:
        for doc in docs:
            world_id = doc.get("world_id")
            if not world_id:
                continue
            await self.worlds.update_one(
                {"world_id": world_id},
                {"$set": doc},
                upsert=True,
            )
