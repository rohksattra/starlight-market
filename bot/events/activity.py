"""Catch-all activity logging for every member interaction with the bot."""
from __future__ import annotations

import discord
from discord.ext import commands

from bot.activity_log import schedule_interaction, schedule_prefix


class ActivityLogEvents(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        schedule_interaction(interaction)

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context) -> None:
        if ctx.interaction is not None:
            return
        schedule_prefix(ctx)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ActivityLogEvents(bot))
