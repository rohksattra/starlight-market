from __future__ import annotations

import discord
from discord.ext import commands

from app.views.slinfo_embed import slinfo_embeds
from utils.command_prefix_feedback import success
from utils.cooldown import check_cooldown

SLINFO_DELETE_AFTER_SECONDS = 300


class Slinfo(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="slinfo")
    async def slinfo(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="slinfo", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            return

        for embed in slinfo_embeds(bot_user=self.bot.user):
            await ctx.send(embed=embed, delete_after=SLINFO_DELETE_AFTER_SECONDS)

        await success(ctx)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Slinfo(bot))
