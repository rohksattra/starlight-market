"""Slash & prefix commands for market features (profile, donation, paid/spent, panels)."""
from __future__ import annotations

import logging
from typing import Final, List, Literal, cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.activity_log import log_activity, person_name
from bot.handlers.games import get_game_handler
from bot.handlers.market import get_market_handler
from bot.handlers.orders import post_transaction_embed
from bot.tier_sync import TierRoleService, schedule_member_tier_sync
from bot.ui.market import (
    PAGE_SIZE,
    ClaimablePaginationView,
    LeaderboardPaginationView,
    MarketStatisticRefreshView,
    PricePaginationView,
    RatedLeaderboardPaginationView,
    claimable_embed,
    donation_embed,
    leaderboard_embed,
    market_statistic_embed,
    price_embed,
    profile_embed,
    rated_leaderboard_embed,
)
from core.tenant import GameContext, get_context
from models.enums import ORDER_MANAGEMENT_ROLES, STAFF_ROLES
from models.games import GAME_TITLES, LEADERBOARD_TYPES, GameType, game_title
from services.economy import EconomyService
from services.items import ItemService
from services.profile import ProfileService
from services.tiers import donor_tier_for_total
from utils.autocomplete import fallback_user_label, user_autocomplete
from utils.confirm_view import ConfirmView
from utils.cooldown import check_cooldown
from utils.discord_safe import safe_defer, safe_respond
from utils.permissions import has_any_role
from utils.prefix_feedback import failed, success

log = logging.getLogger("bot.commands.market")

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


class MarketCommands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.handler = get_market_handler()

    async def item_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        ctx = get_context(interaction.guild.id)
        if ctx is None:
            return []

        items = await ItemService(ctx).list_items()
        results: List[app_commands.Choice[str]] = []
        for item in items:
            name = item.get("item_name", "")
            if current.lower() in name.lower():
                results.append(app_commands.Choice(name=name[:100], value=item["item_id"]))
            if len(results) >= 25:
                break
        return results

    @commands.command(name="mme")
    async def me(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            await failed(ctx)
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="profile_me", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return

        await self._send_profile(ctx, ctx.author, tenant)
        await success(ctx)

    @app_commands.command(name="profile", description="View a member profile")
    @app_commands.describe(member="Select a member")
    async def profile(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="profile_view", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        await safe_defer(interaction, ephemeral=True)
        await self._send_profile(interaction, member, ctx)

    async def _send_profile(
        self,
        ctx_or_interaction: commands.Context | discord.Interaction,
        member: discord.Member,
        tenant: GameContext,
    ) -> None:
        data = await ProfileService(tenant).get_profile_data(user_id=str(member.id))
        embed = profile_embed(member=member, ctx=tenant, **data)

        if isinstance(ctx_or_interaction, commands.Context):
            guild = ctx_or_interaction.guild
            channel = guild.get_channel(tenant.channels.user_profile) if guild else None
            target = channel if isinstance(channel, discord.TextChannel) else ctx_or_interaction.channel
            await target.send(embed=embed)
            return

        guild = ctx_or_interaction.guild
        channel = guild.get_channel(tenant.channels.user_profile) if guild else None
        if isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed)
            await safe_respond(
                ctx_or_interaction,
                content=f"✅ Profile sent to {channel.mention}.",
                ephemeral=True,
            )
            return

        await ctx_or_interaction.followup.send(embed=embed)

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

    @app_commands.command(name="donation", description="(Staff) Record a donation (gold or item value)")
    @app_commands.describe(
        user="Member who donated",
        gold="Gold amount or estimated item value",
        description="Donation or item details",
    )
    @app_commands.autocomplete(user=user_autocomplete)
    async def donation(
        self,
        interaction: discord.Interaction,
        user: str,
        gold: app_commands.Range[int, 1, 2_147_483_647],
        description: str,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid context.", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Only Bot Developer / Bank Manager.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="donation", seconds=3)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        if not user.isdigit():
            await safe_respond(interaction, content="❌ Invalid user ID.", ephemeral=True)
            return

        donor_member = interaction.guild.get_member(int(user))
        if donor_member is None:
            await safe_respond(interaction, content="❌ Member not found in this server.", ephemeral=True)
            return

        if len(description) > 2000:
            await safe_respond(interaction, content="❌ Description is too long (max 2000 characters).", ephemeral=True)
            return

        confirm_embed = discord.Embed(
            title="Confirm Donation",
            description=(
                "Please review the details below.\n"
                "Click **Confirm** to record the donation, or **Cancel**."
            ),
            color=0xFFD700,
        )
        confirm_embed.add_field(name="Donor", value=donor_member.display_name, inline=True)
        confirm_embed.add_field(name="Gold", value=f"{gold:,}", inline=True)
        confirm_embed.add_field(name="Description", value=description.strip()[:1000], inline=False)

        view = ConfirmView(author_id=interaction.user.id, timeout_seconds=30)
        await safe_respond(interaction, embed=confirm_embed, view=view, ephemeral=True)

        confirmed = await view.wait_result()
        if not confirmed:
            await safe_respond(interaction, content="❌ Donation cancelled.", ephemeral=True)
            return

        doc = await EconomyService(ctx).record_donation(user_id=user, gold=gold)
        await TierRoleService(ctx).sync_member(donor_member)

        donation_total = int(doc.get("donation_given", 0) or 0) if doc else 0
        donor_tier_name = donor_tier_for_total(donation_total)
        donor_tier_role_id = (
            ctx.roles.donor_tiers.get(donor_tier_name) if donor_tier_name else None
        )

        ch = interaction.guild.get_channel(ctx.channels.donation)
        if isinstance(ch, discord.TextChannel):
            embed = donation_embed(
                user_id=user,
                gold=gold,
                description=description,
                donor_tier_role_id=donor_tier_role_id,
                ctx=ctx,
            )
            try:
                await ch.send(embed=embed)
            except discord.HTTPException:
                log.exception("Failed to send donation embed | channel=%s", ch.id)

        await safe_respond(
            interaction,
            content="✅ Donation recorded and embed posted.",
            ephemeral=True,
        )
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=f"Added donation of {gold:,} gold for {donor_member.display_name}",
        )

    @app_commands.command(name="paid", description="(Staff) Add manual worker income")
    @app_commands.autocomplete(user=user_autocomplete, item=item_autocomplete)
    async def paid(
        self,
        interaction: discord.Interaction,
        user: str,
        item: str,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid context.", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Only Bot Developer / Bank Manager.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="paid", seconds=3)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        item_doc = await ItemService(ctx).get_by_id(item)
        if not item_doc:
            await safe_respond(interaction, content="❌ Item not found.", ephemeral=True)
            return

        member = interaction.guild.get_member(int(user)) if user.isdigit() else None
        user_label = member.display_name if member else fallback_user_label(user)
        item_name = item_doc.get("item_name", item)

        confirm_embed = discord.Embed(
            title="Confirm Paid",
            description=(
                "Please review the details below.\n"
                "Click **Confirm** to record worker income, or **Cancel**."
            ),
            color=0xFFD700,
        )
        confirm_embed.add_field(name="Worker", value=user_label, inline=True)
        confirm_embed.add_field(name="Item", value=item_name, inline=True)
        confirm_embed.add_field(name="Quantity", value=str(quantity), inline=True)

        view = ConfirmView(author_id=interaction.user.id, timeout_seconds=30)
        await safe_respond(interaction, embed=confirm_embed, view=view, ephemeral=True)

        confirmed = await view.wait_result()
        if not confirmed:
            await safe_respond(interaction, content="❌ Paid cancelled.", ephemeral=True)
            return

        try:
            result = await EconomyService(ctx).paid_worker(
                user_id=user,
                item_id=item,
                quantity=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        schedule_member_tier_sync(interaction.guild, user, ctx)
        await post_transaction_embed(
            guild=interaction.guild,
            ctx=ctx,
            target="worker",
            member=member,
            item_name=str(result["item_name"]),
            item_price=int(result["item_price"]),
            quantity=int(result["quantity"]),
            item_emoji=str(item_doc.get("item_emoji") or "🌟"),
        )
        await safe_respond(
            interaction,
            content=(
                f"✅ Paid recorded\n"
                f"User: `{result['user_id']}`\n"
                f"Item: {result['item_name']}\n"
                f"Qty: {result['quantity']}\n"
                f"Income: **{result['income']:,}**"
            ),
            ephemeral=True,
        )
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"Added manual worker income for {person_name(interaction.guild, user)}: "
                f"{result['quantity']:,}x {result['item_name']} "
                f"({result['income']:,} gold)"
            ),
        )

    @app_commands.command(name="spent", description="(Staff) Add manual customer spending")
    @app_commands.autocomplete(user=user_autocomplete, item=item_autocomplete)
    async def spent(
        self,
        interaction: discord.Interaction,
        user: str,
        item: str,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid context.", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Only Bot Developer / Bank Manager.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="spent", seconds=3)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        item_doc = await ItemService(ctx).get_by_id(item)
        if not item_doc:
            await safe_respond(interaction, content="❌ Item not found.", ephemeral=True)
            return

        member = interaction.guild.get_member(int(user)) if user.isdigit() else None
        user_label = member.display_name if member else fallback_user_label(user)
        item_name = item_doc.get("item_name", item)

        confirm_embed = discord.Embed(
            title="Confirm Spent",
            description=(
                "Please review the details below.\n"
                "Click **Confirm** to record customer spending, or **Cancel**."
            ),
            color=0xFFD700,
        )
        confirm_embed.add_field(name="Customer", value=user_label, inline=True)
        confirm_embed.add_field(name="Item", value=item_name, inline=True)
        confirm_embed.add_field(name="Quantity", value=str(quantity), inline=True)

        view = ConfirmView(author_id=interaction.user.id, timeout_seconds=30)
        await safe_respond(interaction, embed=confirm_embed, view=view, ephemeral=True)

        confirmed = await view.wait_result()
        if not confirmed:
            await safe_respond(interaction, content="❌ Spent cancelled.", ephemeral=True)
            return

        try:
            result = await EconomyService(ctx).spent_customer(
                user_id=user,
                item_id=item,
                quantity=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        schedule_member_tier_sync(interaction.guild, user, ctx)
        await post_transaction_embed(
            guild=interaction.guild,
            ctx=ctx,
            target="customer",
            member=member,
            item_name=str(result["item_name"]),
            item_price=int(result["item_price"]),
            quantity=int(result["quantity"]),
            item_emoji=str(item_doc.get("item_emoji") or "🌟"),
        )
        await safe_respond(
            interaction,
            content=(
                f"✅ Spent recorded\n"
                f"User: `{result['user_id']}`\n"
                f"Item: {result['item_name']}\n"
                f"Qty: {result['quantity']}\n"
                f"Total: **{result['spent']:,}**"
            ),
            ephemeral=True,
        )
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"Added manual customer spending for {person_name(interaction.guild, user)}: "
                f"{result['quantity']:,}x {result['item_name']} "
                f"({result['spent']:,} gold)"
            ),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MarketCommands(bot))
