"""Mongo queries for the monsters collection (scramble hints and battles)."""
from __future__ import annotations

from typing import Any

from database.connection import get_db

MonsterDoc = dict[str, Any]


class MonsterRepo:
    def __init__(self, db_name: str) -> None:
        self.monsters = get_db(db_name).monsters

    async def get_all(self, *, limit: int = 5000) -> list[MonsterDoc]:
        return await self.monsters.find({}, {"_id": 0}).limit(limit).to_list(length=limit)

    async def list_with_health(self, *, min_health: int = 1) -> list[MonsterDoc]:
        cursor = self.monsters.find(
            {"monster_health": {"$gte": min_health}},
            {
                "_id": 0,
                "monster_id": 1,
                "monster_name": 1,
                "monster_health": 1,
                "monster_image": 1,
                "monster_level": 1,
            },
        )
        return [doc async for doc in cursor]
