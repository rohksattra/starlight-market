from __future__ import annotations

import discord
from discord.ext import commands

from core.config import settings
from app.handlers.market_statistic import get_market_statistic_handler
from app.views.market_statistic_button import MarketStatisticRefreshView
from app.views.market_statistic_embed import market_statistic_embed
from utils.cooldown import check_cooldown


class MarketStatistic(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.handler = get_market_statistic_handler()

    async def _fetch_stat_data(self, guild: discord.Guild) -> dict:
        return await self.handler.fetch_stat_data(guild)

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
        embed = market_statistic_embed(**(await self._fetch_stat_data(guild)))
        channel = guild.get_channel(settings.MARKET_STATISTIC_CHANNEL_ID)
        target = channel if isinstance(channel, discord.TextChannel) else ctx.channel
        await target.send(embed=embed, view=MarketStatisticRefreshView())
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
