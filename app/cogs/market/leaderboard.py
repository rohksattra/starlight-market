from __future__ import annotations

import asyncio
from typing import Any, Dict, Final, List, Literal, cast

import discord
from discord import app_commands
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.role_enum import STAFF_ROLE
from app.domains.game_domain import GAME_TITLES, LEADERBOARD_TYPES, GameType
from app.handlers.game import get_game_handler
from app.handlers.leaderboard import get_leaderboard_handler
from app.services.leaderboard_service import LeaderboardService
from app.views.leaderboard_button import LeaderboardPaginationView, PAGE_SIZE
from app.views.leaderboard_embed import leaderboard_embed
from app.views.rated_leaderboard_button import RatedLeaderboardPaginationView
from app.views.rated_leaderboard_embed import rated_leaderboard_embed
from utils.interaction_safe import safe_defer, safe_respond


MarketLeaderboardPanelType = Literal["worker", "customer", "item", "donor", "rated"]

MARKET_LEADERBOARD_PANEL_TYPES: Final[tuple[MarketLeaderboardPanelType, ...]] = (
    "worker",
    "customer",
    "item",
    "donor",
    "rated",
)

MARKET_LEADERBOARD_CHANNELS: Final[Dict[MarketLeaderboardPanelType, int]] = {
    "worker": settings.TOP_EARNING_WORKER_CHANNEL_ID,
    "customer": settings.TOP_SPENDING_CUSTOMER_CHANNEL_ID,
    "item": settings.TOP_ITEM_CHANNEL_ID,
    "donor": settings.TOP_DONOR_CHANNEL_ID,
    "rated": settings.TOP_RATED_WORKER_CHANNEL_ID,
}

MARKET_LEADERBOARD_TITLES: Final[Dict[MarketLeaderboardPanelType, str]] = {
    "worker": "🏆 Top 100 Workers",
    "customer": "🏅 Top 100 Customers",
    "item": "🛒 Top 100 Items",
    "donor": "🎁 Top 100 Donors",
    "rated": "⭐ Top Rated Workers",
}

LEADERBOARD_CHOICES: Final[list[app_commands.Choice[str]]] = [
    app_commands.Choice(name="Top Workers", value="worker"),
    app_commands.Choice(name="Top Customers", value="customer"),
    app_commands.Choice(name="Top Items", value="item"),
    app_commands.Choice(name="Top Donors", value="donor"),
    app_commands.Choice(name="Top Rated Workers", value="rated"),
    *[
        app_commands.Choice(name=GAME_TITLES[game_type], value=game_type)
        for game_type in LEADERBOARD_TYPES
    ],
]


def _is_game_leaderboard(lb_type: str) -> bool:
    return lb_type in LEADERBOARD_TYPES


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.leaderboard_serv = LeaderboardService()
        self.handler = get_leaderboard_handler()

    def _ensure_staff(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        return has_any_role(interaction.user, STAFF_ROLE)

    async def _send_game_leaderboard_panel(
        self,
        *,
        channel: discord.TextChannel,
        game_type: GameType,
    ) -> discord.Message:
        return await get_game_handler(self.bot).send_leaderboard_panel(
            channel=channel,
            game_type=game_type,
        )

    def _resolve_market_channel(
        self,
        guild: discord.Guild,
        lb_type: MarketLeaderboardPanelType,
    ) -> discord.TextChannel | None:
        channel = guild.get_channel(MARKET_LEADERBOARD_CHANNELS[lb_type])
        return channel if isinstance(channel, discord.TextChannel) else None

    def _resolve_game_leaderboard_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel = guild.get_channel(settings.GAME_LEADERBOARD_CHANNEL_ID)
        return channel if isinstance(channel, discord.TextChannel) else None

    def _resolve_channel(
        self,
        guild: discord.Guild,
        lb_type: str,
    ) -> discord.TextChannel | None:
        if _is_game_leaderboard(lb_type):
            return self._resolve_game_leaderboard_channel(guild)
        return self._resolve_market_channel(guild, cast(MarketLeaderboardPanelType, lb_type))

    def _display_name(self, lb_type: str) -> str:
        if _is_game_leaderboard(lb_type):
            return GAME_TITLES[cast(GameType, lb_type)]
        return MARKET_LEADERBOARD_TITLES[cast(MarketLeaderboardPanelType, lb_type)]

    async def _fetch_worker(self) -> List[Dict[str, Any]]:
        guild = self.bot.get_guild(settings.GUILD_ID)
        return await self.handler.fetch_worker(guild)

    async def _fetch_customer(self) -> List[Dict[str, Any]]:
        guild = self.bot.get_guild(settings.GUILD_ID)
        return await self.handler.fetch_customer(guild)

    async def _fetch_donor(self) -> List[Dict[str, Any]]:
        guild = self.bot.get_guild(settings.GUILD_ID)
        return await self.handler.fetch_donor(guild)

    async def _fetch_item(self) -> List[Dict[str, Any]]:
        return await self.handler.fetch_item()

    async def _fetch_rated_workers(self) -> List[Dict[str, Any]]:
        guild = self.bot.get_guild(settings.GUILD_ID)
        return await self.handler.fetch_rated_workers(guild)

    async def _fetch_market_entries(self, lb_type: MarketLeaderboardPanelType) -> List[Dict[str, Any]]:
        if lb_type == "worker":
            return await self._fetch_worker()
        if lb_type == "customer":
            return await self._fetch_customer()
        if lb_type == "donor":
            return await self._fetch_donor()
        if lb_type == "item":
            return await self._fetch_item()
        return await self._fetch_rated_workers()

    async def _send_market_leaderboard_panel(
        self,
        *,
        channel: discord.TextChannel,
        lb_type: MarketLeaderboardPanelType,
    ) -> discord.Message:
        entries = await self._fetch_market_entries(lb_type)
        title = MARKET_LEADERBOARD_TITLES[lb_type]

        if lb_type == "rated":
            view = RatedLeaderboardPaginationView(page=0)
            view.set_initial_state(total_items=len(entries))
            return await channel.send(
                embed=rated_leaderboard_embed(
                    title=title,
                    entries=entries,
                    page=0,
                    page_size=PAGE_SIZE,
                ),
                view=view,
            )

        view = LeaderboardPaginationView(lb_type=lb_type, title=title)
        view.set_initial_state(total_items=len(entries))
        return await channel.send(
            embed=leaderboard_embed(
                title=title,
                entries=entries,
                lb_type=lb_type,
                page=0,
                page_size=PAGE_SIZE,
            ),
            view=view,
        )

    async def _send_leaderboard_panel(
        self,
        *,
        channel: discord.TextChannel,
        lb_type: str,
    ) -> discord.Message:
        if _is_game_leaderboard(lb_type):
            return await self._send_game_leaderboard_panel(
                channel=channel,
                game_type=cast(GameType, lb_type),
            )
        return await self._send_market_leaderboard_panel(
            channel=channel,
            lb_type=cast(MarketLeaderboardPanelType, lb_type),
        )

    @app_commands.command(
        name="leaderboard-panel",
        description="Post a persistent leaderboard panel to its configured channel.",
    )
    @app_commands.describe(leaderboard="Leaderboard type to post")
    @app_commands.choices(leaderboard=LEADERBOARD_CHOICES)
    async def leaderboard_panel(
        self,
        interaction: discord.Interaction,
        leaderboard: app_commands.Choice[str],
    ) -> None:
        if not self._ensure_staff(interaction):
            await safe_respond(
                interaction,
                content="❌ You don't have permission to use this command.",
                ephemeral=True,
            )
            return
        if interaction.guild is None:
            await safe_respond(interaction, content="❌ Use this command in a server.", ephemeral=True)
            return

        lb_type = leaderboard.value
        channel = self._resolve_channel(interaction.guild, lb_type)
        if channel is None:
            await safe_respond(
                interaction,
                content=f"❌ Channel for **{self._display_name(lb_type)}** is not configured or not found.",
                ephemeral=True,
            )
            return

        await safe_defer(interaction, ephemeral=True)
        await self._send_leaderboard_panel(channel=channel, lb_type=lb_type)
        await safe_respond(
            interaction,
            content=f"✅ **{leaderboard.name}** panel posted in {channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="leaderboard-panel-all",
        description="Post all persistent leaderboard panels (market + game).",
    )
    async def leaderboard_panel_all(self, interaction: discord.Interaction) -> None:
        if not self._ensure_staff(interaction):
            await safe_respond(
                interaction,
                content="❌ You don't have permission to use this command.",
                ephemeral=True,
            )
            return
        if interaction.guild is None:
            await safe_respond(interaction, content="❌ Use this command in a server.", ephemeral=True)
            return

        missing: list[str] = []
        for lb_type in MARKET_LEADERBOARD_PANEL_TYPES:
            if self._resolve_market_channel(interaction.guild, lb_type) is None:
                missing.append(MARKET_LEADERBOARD_TITLES[lb_type])

        game_channel = self._resolve_game_leaderboard_channel(interaction.guild)
        if game_channel is None:
            missing.append("Game Leaderboards (GAME_LEADERBOARD_CHANNEL_ID)")

        if missing:
            await safe_respond(
                interaction,
                content="❌ Some leaderboard channels are not configured:\n" + "\n".join(f"• {t}" for t in missing),
                ephemeral=True,
            )
            return

        await safe_defer(interaction, ephemeral=True)

        tasks: list[asyncio.Task[discord.Message]] = []
        for lb_type in MARKET_LEADERBOARD_PANEL_TYPES:
            channel = self._resolve_market_channel(interaction.guild, lb_type)
            if channel is not None:
                tasks.append(
                    asyncio.create_task(
                        self._send_leaderboard_panel(channel=channel, lb_type=lb_type)
                    )
                )

        for game_type in LEADERBOARD_TYPES:
            tasks.append(
                asyncio.create_task(
                    self._send_leaderboard_panel(channel=game_channel, lb_type=game_type)
                )
            )

        await asyncio.gather(*tasks)

        total = len(MARKET_LEADERBOARD_PANEL_TYPES) + len(LEADERBOARD_TYPES)
        await safe_respond(
            interaction,
            content=(
                f"✅ Posted **{total}** leaderboard panel(s) "
                f"({len(MARKET_LEADERBOARD_PANEL_TYPES)} market + {len(LEADERBOARD_TYPES)} game)."
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Leaderboard(bot))
