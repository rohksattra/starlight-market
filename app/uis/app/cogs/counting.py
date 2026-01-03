# app/cogs/counting.py
from __future__ import annotations

import discord
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.services.counting_service import CountingService


class Counting(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.serv = CountingService()
        self.channel_id = settings.COUNTING_CHANNEL_ID
        self.current_answer: int | None = None
        self.current_question: str | None = None

    @commands.command(name="counting")
    async def counting(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return
        if not has_any_role(ctx.author, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Staff only.", delete_after=5)
            return
        channel = ctx.guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Counting channel not configured.", delete_after=5)
            return
        if self.current_answer is not None:
            await ctx.send("⚠️ Counting is already running.", delete_after=5)
            return
        q, ans = self.serv.generate()
        self.current_question = q
        self.current_answer = ans
        await channel.send(f"🧠 Count:\n\n`{q}`")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is None:
            return
        if message.channel.id != self.channel_id:
            return
        if self.current_answer is None:
            return
        if not message.content.lstrip("-").isdigit():
            return
        if int(message.content) == self.current_answer:
            await message.add_reaction("✅")
            q, ans = self.serv.generate()
            self.current_question = q
            self.current_answer = ans
            await message.channel.send(f"🧠 Count:\n\n`{q}`")
        else:
            await message.add_reaction("❌")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Counting(bot))
