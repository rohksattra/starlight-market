"""Button/modal/select callbacks for market features."""
from __future__ import annotations

from typing import Any, Literal

import discord

from core.tenant import GameContext, get_context
from services.market import MarketService

MarketLBType = Literal["worker", "customer", "item", "donor", "rated"]
MAX_ITEMS = 100


class MarketHandler:
    def _member_name(self, guild: discord.Guild | None, user_id: str) -> str:
        if guild is None:
            return "Unknown"
        try:
            member = guild.get_member(int(user_id))
        except (TypeError, ValueError):
            return "Unknown"
        return member.display_name if member else "Unknown"

    def _resolve_ctx(self, guild: discord.Guild | None) -> GameContext | None:
        if guild is None:
            return None
        return get_context(guild.id)

    async def fetch_claimable(self, guild: discord.Guild | None) -> list[dict[str, Any]]:
        ctx = self._resolve_ctx(guild)
        if ctx is None:
            return []
        return await MarketService(ctx).list_claimable()

    async def fetch_stat_data(self, guild: discord.Guild) -> dict[str, Any]:
        ctx = get_context(guild.id)
        if ctx is None:
            return {
                "guild": guild,
                "order": {},
                "gold": {},
                "leaderboard": {},
                "total_workers": 0,
                "total_customers": 0,
            }

        try:
            data = await MarketService(ctx).market_statistic()
        except ValueError:
            data = {"order": {}, "gold": {}, "leaderboard": {}}

        worker_role = guild.get_role(ctx.roles.worker)
        customer_role = guild.get_role(ctx.roles.customer)
        members = guild.members or []
        total_workers = sum(1 for m in members if worker_role and worker_role in m.roles)
        total_customers = sum(1 for m in members if customer_role and customer_role in m.roles)

        return {
            "guild": guild,
            "order": data.get("order", {}),
            "gold": data.get("gold", {}),
            "leaderboard": data.get("leaderboard", {}),
            "total_workers": total_workers,
            "total_customers": total_customers,
        }

    async def fetch_worker(self, guild: discord.Guild | None) -> list[dict[str, Any]]:
        ctx = self._resolve_ctx(guild)
        if ctx is None:
            return []
        rows = await MarketService(ctx).top_workers()
        return [{"name": self._member_name(guild, r["id"]), "value": r["value"]} for r in rows]

    async def fetch_customer(self, guild: discord.Guild | None) -> list[dict[str, Any]]:
        ctx = self._resolve_ctx(guild)
        if ctx is None:
            return []
        rows = await MarketService(ctx).top_customers()
        return [{"name": self._member_name(guild, r["id"]), "value": r["value"]} for r in rows]

    async def fetch_donor(self, guild: discord.Guild | None) -> list[dict[str, Any]]:
        ctx = self._resolve_ctx(guild)
        if ctx is None:
            return []
        rows = await MarketService(ctx).top_donors()
        return [{"name": self._member_name(guild, r["id"]), "value": r["value"]} for r in rows]

    async def fetch_item(self, guild: discord.Guild | None) -> list[dict[str, Any]]:
        ctx = self._resolve_ctx(guild)
        if ctx is None:
            return []
        return await MarketService(ctx).top_items()

    async def fetch_rated_workers(self, guild: discord.Guild | None) -> list[dict[str, Any]]:
        ctx = self._resolve_ctx(guild)
        if ctx is None:
            return []
        rows = await MarketService(ctx).top_rated_workers()
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
        lb_type: MarketLBType,
        guild: discord.Guild | None,
    ) -> list[dict[str, Any]]:
        if lb_type == "worker":
            return (await self.fetch_worker(guild))[:MAX_ITEMS]
        if lb_type == "customer":
            return (await self.fetch_customer(guild))[:MAX_ITEMS]
        if lb_type == "donor":
            return (await self.fetch_donor(guild))[:MAX_ITEMS]
        if lb_type == "item":
            return (await self.fetch_item(guild))[:MAX_ITEMS]
        return (await self.fetch_rated_workers(guild))[:MAX_ITEMS]


_handler: MarketHandler | None = None


def get_market_handler() -> MarketHandler:
    global _handler
    if _handler is None:
        _handler = MarketHandler()
    return _handler
