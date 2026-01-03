# app/cogs/market_statistic.py
from __future__ import annotations

import discord
from discord.ext import commands

from core.role_map import get_discord_role
from app.domains.enums.role_enum import ServerRole
from app.services.statistic_service import StatisticService
from app.uis.market_statistic_embed import market_statistic_embed
from utils.cooldown import check_cooldown


class MarketStatistic(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.statistic_serv = StatisticService()

    @commands.command(name="mstat")
    async def market_stat(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return
        try:
            check_cooldown(user_id=ctx.author.id, key="market_stat", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            return
        guild = ctx.guild
        try:
            data = await self.statistic_serv.market_statistic()
        except ValueError:
            data = {"order": {}, "gold": {}, "leaderboard": {}}
        worker_role = get_discord_role(guild, ServerRole.WORKER)
        customer_role = get_discord_role(guild, ServerRole.CUSTOMER)
        members = guild.members or []
        total_workers = sum(1 for m in members if worker_role and worker_role in m.roles)
        total_customers = sum(1 for m in members if customer_role and customer_role in m.roles)
        embed = market_statistic_embed(
            guild=guild, order=data.get("order", {}),
            gold=data.get("gold", {}),
            leaderboard=data.get("leaderboard", {}),
            total_workers=total_workers,
            total_customers=total_customers,
        )
        await ctx.send(embed=embed, delete_after=180)
        try:
            await ctx.message.add_reaction("✅")
        except discord.Forbidden:
            pass
        try:
            await ctx.message.delete(delay=5)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MarketStatistic(bot))
