"""Mongo queries for the monsters collection (scramble hints)."""
from __future__ import annotations

from typing import Any

from database.connection import get_db

MonsterDoc = dict[str, Any]


class MonsterRepo:
    def __init__(self, db_name: str) -> None:
        self.monsters = get_db(db_name).monsters

    async def get_all(self, *, limit: int = 5000) -> list[MonsterDoc]:
        return await self.monsters.find({}, {"_id": 0}).limit(limit).to_list(length=limit)
