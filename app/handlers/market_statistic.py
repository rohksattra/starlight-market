from __future__ import annotations

import discord

from core.role_map import get_discord_role
from app.domains.enums.role_enum import ServerRole
from app.services.statistic_service import StatisticService


class MarketStatisticHandler:
    def __init__(self) -> None:
        self.statistic_serv = StatisticService()

    async def fetch_stat_data(self, guild: discord.Guild) -> dict:
        try:
            data = await self.statistic_serv.market_statistic()
        except ValueError:
            data = {"order": {}, "gold": {}, "leaderboard": {}}

        worker_role = get_discord_role(guild, ServerRole.WORKER)
        customer_role = get_discord_role(guild, ServerRole.CUSTOMER)
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


_handler: MarketStatisticHandler | None = None


def get_market_statistic_handler() -> MarketStatisticHandler:
    global _handler
    if _handler is None:
        _handler = MarketStatisticHandler()
    return _handler
