from __future__ import annotations

from typing import Any, Dict, List

from db.mongo import get_db


MonsterData = Dict[str, Any]


class MonsterRepository:
    def __init__(self) -> None:
        self.monsters = get_db().monsters

    async def get_all(self, *, limit: int = 5000) -> List[MonsterData]:
        return await self.monsters.find(
            {},
            {"_id": 0},
        ).limit(limit).to_list(length=limit)