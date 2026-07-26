from __future__ import annotations

from typing import Any, Dict, List, Literal, cast

import discord

from core.config import settings
from app.services.leaderboard_service import LeaderboardService


MarketLeaderboardType = Literal["worker", "customer", "item", "donor", "rated"]


class LeaderboardHandler:
    def __init__(self) -> None:
        self.leaderboard_serv = LeaderboardService()

    def _member_name(self, guild: discord.Guild | None, user_id: str) -> str:
        if guild is None:
            return "Unknown"
        member = guild.get_member(int(user_id))
        return member.display_name if member else "Unknown"

    async def fetch_worker(self, guild: discord.Guild | None) -> List[Dict[str, Any]]:
        rows = await self.leaderboard_serv.top_workers()
        return [{"name": self._member_name(guild, r["id"]), "value": r["value"]} for r in rows]

    async def fetch_customer(self, guild: discord.Guild | None) -> List[Dict[str, Any]]:
        rows = await self.leaderboard_serv.top_customers()
        return [{"name": self._member_name(guild, r["id"]), "value": r["value"]} for r in rows]

    async def fetch_donor(self, guild: discord.Guild | None) -> List[Dict[str, Any]]:
        rows = await self.leaderboard_serv.top_donors()
        return [{"name": self._member_name(guild, r["id"]), "value": r["value"]} for r in rows]

    async def fetch_item(self) -> List[Dict[str, Any]]:
        return await self.leaderboard_serv.top_items()

    async def fetch_rated_workers(self, guild: discord.Guild | None) -> List[Dict[str, Any]]:
        rows = await self.leaderboard_serv.top_rated_workers()
        return [
            {
                "name": self._member_name(guild, r["id"]),
                "avg": float(r.get("avg", 0)),
                "count": int(r.get("count", 0)),
            }
            for r in rows
        ]

    async def fetch_entries(
        self,
        lb_type: MarketLeaderboardType,
        guild: discord.Guild | None,
    ) -> List[Dict[str, Any]]:
        if lb_type == "worker":
            return await self.fetch_worker(guild)
        if lb_type == "customer":
            return await self.fetch_customer(guild)
        if lb_type == "donor":
            return await self.fetch_donor(guild)
        if lb_type == "item":
            return await self.fetch_item()
        return await self.fetch_rated_workers(guild)

    async def fetch_market_lb(
        self,
        lb_type: Literal["worker", "customer", "item", "donor"],
        guild: discord.Guild | None,
    ) -> List[Dict[str, Any]]:
        return await self.fetch_entries(cast(MarketLeaderboardType, lb_type), guild)


_handler: LeaderboardHandler | None = None


def get_leaderboard_handler() -> LeaderboardHandler:
    global _handler
    if _handler is None:
        _handler = LeaderboardHandler()
    return _handler


def resolve_guild(interaction: discord.Interaction) -> discord.Guild | None:
    if interaction.guild is not None:
        return interaction.guild
    from discord.ext import commands

    bot = interaction.client
    if isinstance(bot, commands.Bot):
        return bot.get_guild(settings.GUILD_ID)
    return None
