# app/cogs/claimable.py
from __future__ import annotations

import discord
from discord.ext import commands

from app.services.claimable_service import ClaimableService
from app.uis.claimable_button import ClaimablePaginationView
from app.uis.claimable_embed import claimable_embed
from utils.cooldown import check_cooldown
from utils.command_prefix_feedback import failed, success


class Claimable(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = ClaimableService()

    async def _validate_ctx(self, ctx: commands.Context):
        if ctx.guild is None:
            return None

        try:
            check_cooldown(user_id=ctx.author.id, key="claimable", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return None

        return ctx.guild

    async def _fetch_claimable(self) -> list[dict]:
        return await self.service.list_claimable()

    @commands.command(name="claimable")
    async def claimable(self, ctx: commands.Context):
        guild = await self._validate_ctx(ctx)
        if guild is None:
            return

        entries = await self._fetch_claimable()

        view = ClaimablePaginationView()
        view.set_initial_state(total_items=len(entries))

        await ctx.send(
            embed=claimable_embed(
                entries=entries,
                page=0,
                page_size=25,
            ),
            view=view,
        )

        await success(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(Claimable(bot))