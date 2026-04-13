# app/services/leaderboard_service.py
from __future__ import annotations
from typing import Any, Dict, List

from app.repositories.leaderboard_repo import LeaderboardRepository
from app.repositories.item_repo import ItemRepository


class LeaderboardService:
    def __init__(self) -> None:
        self.leaderboards = LeaderboardRepository()
        self.items = ItemRepository()

    async def top_workers(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        return await self.leaderboards.top_workers(limit=limit)

    async def top_customers(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        return await self.leaderboards.top_customers(limit=limit)

    async def _inject_item_emoji(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not rows:
            return rows

        item_ids = [r["item_id"] for r in rows]

        db_items = await self.items.get_all()
        emoji_map = {
            i["item_id"]: i.get("item_emoji", "🌟")
            for i in db_items
            if i["item_id"] in item_ids
        }

        for r in rows:
            r["item_emoji"] = emoji_map.get(r["item_id"], "🌟")

        return rows

    async def top_items(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        rows = await self.leaderboards.top_items(limit=limit)
        return await self._inject_item_emoji(rows)