from __future__ import annotations

import discord
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.services.counting_service import CountingService
from app.repositories.user_repo import UserRepository
from app.services.leaderboard_service import LeaderboardService
from app.uis.counting_leaderboard_button import CountingLeaderboardPaginationView
from app.uis.counting_leaderboard_embed import counting_leaderboard_embed


class Counting(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.serv = CountingService()
        self.users = UserRepository()
        self.leaderboard = LeaderboardService()
        self.channel_id = settings.COUNTING_CHANNEL_ID
        self.current_answer: int | None = None
        self.current_question: str | None = None
        self.lb_channel_id = settings.TOP_COUNTING_SCORE_CHANNEL_ID

    async def _fetch_counting_top(self) -> list[dict]:
        rows = await self.leaderboard.top_counting_scores()
        guild = self.bot.get_guild(settings.GUILD_ID)
        result = []
        for r in rows:
            member = guild.get_member(int(r["id"])) if guild else None
            name = member.display_name if member else "Unknown"
            result.append({"name": name, "value": int(r.get("value", 0))})
        return result

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

    @commands.command(name="countlb")
    async def counting_leaderboard(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return
        if not has_any_role(ctx.author, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Staff only.", delete_after=5)
            return
        channel = ctx.guild.get_channel(self.lb_channel_id)
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Counting leaderboard channel not configured.", delete_after=5)
            return

        entries = await self._fetch_counting_top()
        view = CountingLeaderboardPaginationView(page=0)
        view.set_initial_state(total_items=len(entries))

        await channel.send(
            embed=counting_leaderboard_embed(
                title="🔢 Top Counting Score",
                entries=entries,
                page=0,
                page_size=25,
            ),
            view=view,
        )

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
            user_id = str(message.author.id)
            await self.users.ensure_user(user_id)
            await self.users.inc_counting_score(user_id=user_id, points=2)
            q, ans = self.serv.generate()
            self.current_question = q
            self.current_answer = ans
            await message.channel.send(f"🧠 Count:\n\n`{q}`")
        else:
            await message.add_reaction("❌")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Counting(bot))
