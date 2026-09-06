"""Market prefix panels and leaderboard-panel command."""
from __future__ import annotations

from typing import Final, Literal, cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.handlers.games import get_game_handler
from bot.ui.market import (
    PAGE_SIZE,
    ClaimablePaginationView,
    LeaderboardPaginationView,
    MarketStatisticRefreshView,
    PricePaginationView,
    RatedLeaderboardPaginationView,
    claimable_embed,
    leaderboard_embed,
    market_statistic_embed,
    price_embed,
    rated_leaderboard_embed,
)
from core.tenant import GameContext, get_context
from models.enums import ORDER_MANAGEMENT_ROLES, STAFF_ROLES
from models.games import GAME_TITLES, LEADERBOARD_TYPES, GameType, game_title
from services.items import ItemService
from utils.cooldown import check_cooldown
from utils.discord_safe import safe_defer, safe_respond
from utils.permissions import has_any_role
from utils.prefix_feedback import failed, success

MarketLeaderboardPanelType = Literal["worker", "customer", "item", "donor", "rated"]

MARKET_LEADERBOARD_PANEL_TYPES: Final[tuple[MarketLeaderboardPanelType, ...]] = (
    "worker",
    "customer",
    "item",
    "donor",
    "rated",
)

MARKET_LEADERBOARD_TITLES: Final[dict[MarketLeaderboardPanelType, str]] = {
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


def _channel_id_for_lb(ctx: GameContext, lb_type: MarketLeaderboardPanelType) -> int:
    mapping = {
        "worker": ctx.channels.top_earning_worker,
        "customer": ctx.channels.top_spending_customer,
        "item": ctx.channels.top_item,
        "donor": ctx.channels.top_donor,
        "rated": ctx.channels.top_rated_worker,
    }
    return mapping[lb_type]


class MarketPanelMixin:
    @commands.command(name="mprice")
    async def price(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            await failed(ctx)
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="price", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return

        if not has_any_role(ctx.author, tenant, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Staff only.", delete_after=5)
            await failed(ctx)
            return

        item_serv = ItemService(tenant)
        categories = await item_serv.list_categories()
        if not categories:
            await ctx.send("⚠️ No item categories available.", delete_after=5)
            await failed(ctx)
            return

        price_channel = ctx.guild.get_channel(tenant.channels.price)
        if not isinstance(price_channel, discord.TextChannel):
            await ctx.send("❌ Price channel is not configured correctly.", delete_after=5)
            await failed(ctx)
            return

        for category in categories:
            items = await item_serv.list_item_price_by_category(category)
            if not items:
                continue
            view = PricePaginationView(category=category)
            view.set_initial_state(total_items=len(items))
            await price_channel.send(
                embed=price_embed(category=category, items=items, page=0, ctx=tenant),
                view=view,
            )

        await success(ctx)

    @commands.command(name="mstat")
    async def mstat(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="market_stat", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            return

        embed = market_statistic_embed(**(await self.handler.fetch_stat_data(ctx.guild)))
        channel = ctx.guild.get_channel(tenant.channels.market_statistic)
        target = channel if isinstance(channel, discord.TextChannel) else ctx.channel
        await target.send(embed=embed, view=MarketStatisticRefreshView())
        await success(ctx)

    @commands.command(name="mclaimable")
    async def claimable(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            await failed(ctx)
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="claimable", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return

        entries = await self.handler.fetch_claimable(ctx.guild)
        view = ClaimablePaginationView()
        view.set_initial_state(total_items=len(entries))
        await ctx.send(
            embed=claimable_embed(entries=entries, page=0, page_size=PAGE_SIZE, ctx=tenant),
            view=view,
        )
        await success(ctx)

    def _resolve_market_channel(
        self,
        guild: discord.Guild,
        tenant: GameContext,
        lb_type: MarketLeaderboardPanelType,
    ) -> discord.TextChannel | None:
        channel = guild.get_channel(_channel_id_for_lb(tenant, lb_type))
        return channel if isinstance(channel, discord.TextChannel) else None

    def _resolve_game_leaderboard_channel(
        self,
        guild: discord.Guild,
        tenant: GameContext,
    ) -> discord.TextChannel | None:
        channel = guild.get_channel(tenant.channels.game_leaderboard)
        return channel if isinstance(channel, discord.TextChannel) else None

    def _resolve_channel(
        self,
        guild: discord.Guild,
        tenant: GameContext,
        lb_type: str,
    ) -> discord.TextChannel | None:
        if _is_game_leaderboard(lb_type):
            return self._resolve_game_leaderboard_channel(guild, tenant)
        return self._resolve_market_channel(
            guild,
            tenant,
            cast(MarketLeaderboardPanelType, lb_type),
        )

    def _display_name(self, lb_type: str, tenant: GameContext | None = None) -> str:
        if _is_game_leaderboard(lb_type):
            points_name = tenant.brand.points_name if tenant else None
            return game_title(cast(GameType, lb_type), points_name=points_name)
        return MARKET_LEADERBOARD_TITLES[cast(MarketLeaderboardPanelType, lb_type)]

    async def _send_market_leaderboard_panel(
        self,
        *,
        channel: discord.TextChannel,
        lb_type: MarketLeaderboardPanelType,
    ) -> discord.Message:
        entries = await self.handler.fetch_entries(lb_type, channel.guild)
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
                    period="all",
                    ctx=get_context(channel.guild.id),
                ),
                view=view,
            )

        view = LeaderboardPaginationView(
            lb_type=cast(Literal["worker", "customer", "item", "donor"], lb_type),
            title=title,
        )
        view.set_initial_state(total_items=len(entries))
        return await channel.send(
            embed=leaderboard_embed(
                title=title,
                entries=entries,
                lb_type=cast(Literal["worker", "customer", "item", "donor"], lb_type),
                page=0,
                page_size=PAGE_SIZE,
                period="all",
                ctx=get_context(channel.guild.id),
            ),
            view=view,
        )

    async def _send_leaderboard_panel(
        self,
        *,
        channel: discord.TextChannel,
        tenant: GameContext,
        lb_type: str,
    ) -> discord.Message:
        if _is_game_leaderboard(lb_type):
            return await get_game_handler(self.bot).send_leaderboard_panel(
                channel=channel,
                ctx=tenant,
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
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Use this command in a server.", ephemeral=True)
            return

        tenant = get_context(interaction.guild.id)
        if tenant is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, tenant, STAFF_ROLES):
            await safe_respond(
                interaction,
                content="❌ You don't have permission to use this command.",
                ephemeral=True,
            )
            return

        lb_type = leaderboard.value
        channel = self._resolve_channel(interaction.guild, tenant, lb_type)
        if channel is None:
            await safe_respond(
                interaction,
                content=(
                    f"❌ Channel for **{self._display_name(lb_type, tenant)}** "
                    "is not configured or not found."
                ),
                ephemeral=True,
            )
            return

        await safe_defer(interaction, ephemeral=True)
        await self._send_leaderboard_panel(channel=channel, tenant=tenant, lb_type=lb_type)
        await safe_respond(
            interaction,
            content=f"✅ **{leaderboard.name}** panel posted in {channel.mention}.",
            ephemeral=True,
        )
