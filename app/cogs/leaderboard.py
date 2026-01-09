# app/cogs/leaderboard.py
from __future__ import annotations

from typing import Any, cast, Dict, List

import discord
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.services.leaderboard_service import LeaderboardService
from app.uis.leaderboard_button import LeaderboardPaginationView
from app.uis.leaderboard_embed import leaderboard_embed
from utils.command_prefix_feedback import failed, success
from utils.cooldown import check_cooldown


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.leaderboard_serv = LeaderboardService()

    def _is_staff(self, member: discord.Member) -> bool:
        return has_any_role(member, ORDER_MANAGEMENT_ROLES)

    async def _validate_ctx(self, ctx: commands.Context) -> discord.Guild | None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return None
        try:
            check_cooldown(user_id=ctx.author.id, key="leaderboard", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return None
        if not self._is_staff(ctx.author):
            await ctx.send("❌ Staff only.", delete_after=5)
            await failed(ctx)
            return None
        return ctx.guild

    def _get_channel(self, guild: discord.Guild | None, lb_type: str) -> discord.TextChannel | None:
        if guild is None:
            return None
        channel_id = {"worker": settings.TOP_WORKER_CHANNEL_ID, "customer": settings.TOP_CUSTOMER_CHANNEL_ID, "item": settings.TOP_ITEM_CHANNEL_ID}.get(lb_type)
        if not channel_id:
            return None
        channel = guild.get_channel(channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _fetch_worker(self) -> List[Dict[str, Any]]:
        rows = await self.leaderboard_serv.top_workers()
        guild = self.bot.get_guild(settings.GUILD_ID)
        result = []
        for r in rows:
            member = guild.get_member(int(r["id"])) if guild else None
            result.append({"name": member.display_name if member else "Unknown", "value": r["value"]})
        return result

    async def _fetch_customer(self) -> List[Dict[str, Any]]:
        rows = await self.leaderboard_serv.top_customers()
        guild = self.bot.get_guild(settings.GUILD_ID)
        result = []
        for r in rows:
            member = guild.get_member(int(r["id"])) if guild else None
            result.append({"name": member.display_name if member else "Unknown", "value": r["value"]})
        return result

    async def _fetch_item(self) -> List[Dict[str, Any]]:
        return cast(List[Dict[str, Any]], await self.leaderboard_serv.top_items())

    @commands.command(name="lbw")
    async def leaderboard_worker(self, ctx: commands.Context) -> None:
        guild = await self._validate_ctx(ctx)
        if guild is None:
            return
        channel = self._get_channel(guild, "worker")
        if channel is None:
            await ctx.send("❌ Worker leaderboard channel not found.", delete_after=5)
            await failed(ctx)
            return
        entries = await self._fetch_worker()
        await channel.send(
            embed=leaderboard_embed(title="🏆 Top 100 Workers", entries=entries, lb_type="worker", page=0, page_size=25),
            view=LeaderboardPaginationView(lb_type="worker", title="🏆 Top 100 Workers"),
        )
        await success(ctx)

    @commands.command(name="lbc")
    async def leaderboard_customer(self, ctx: commands.Context) -> None:
        guild = await self._validate_ctx(ctx)
        if guild is None:
            return
        channel = self._get_channel(guild, "customer")
        if channel is None:
            await ctx.send("❌ Customer leaderboard channel not found.", delete_after=5)
            await failed(ctx)
            return
        entries = await self._fetch_customer()
        await channel.send(
            embed=leaderboard_embed(title="🏅 Top 100 Customers", entries=entries, lb_type="customer", page=0, page_size=25),
            view=LeaderboardPaginationView(lb_type="customer", title="🏅 Top 100 Customers"),
        )
        await success(ctx)

    @commands.command(name="lbi")
    async def leaderboard_item(self, ctx: commands.Context) -> None:
        guild = await self._validate_ctx(ctx)
        if guild is None:
            return
        channel = self._get_channel(guild, "item")
        if channel is None:
            await ctx.send("❌ Item leaderboard channel not found.", delete_after=5)
            await failed(ctx)
            return
        entries = await self._fetch_item()
        await channel.send(
            embed=leaderboard_embed(title="🛒 Top 100 Items", entries=entries, lb_type="item", page=0, page_size=25),
            view=LeaderboardPaginationView(lb_type="item", title="🛒 Top 100 Items"),
        )
        await success(ctx)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Leaderboard(bot))
