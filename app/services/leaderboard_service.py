# app/services/leaderboard_service.py
from __future__ import annotations
from typing import Any, Dict, List

from app.repositories.leaderboard_repo import LeaderboardRepository


class LeaderboardService:
    def __init__(self) -> None:
        self.leaderboards = LeaderboardRepository()

    async def top_workers(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        return await self.leaderboards.top_workers(limit=limit)

    async def top_customers(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        return await self.leaderboards.top_customers(limit=limit)

    async def top_items(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        return await self.leaderboards.top_items(limit=limit)
