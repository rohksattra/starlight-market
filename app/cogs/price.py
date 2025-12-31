# app/cogs/price.py
from __future__ import annotations

from typing import List

import discord
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.services.item_service import ItemService
from app.uis.price_embed import price_embed
from app.uis.price_button import PriceRefreshView
from utils.command_prefix_feedback import success, failed
from utils.cooldown import check_cooldown


class Price(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.item_serv = ItemService()

    def _is_staff(self, member: discord.Member) -> bool:
        return has_any_role(member, ORDER_MANAGEMENT_ROLES)

    async def _validate_ctx(self, ctx: commands.Context) -> discord.Guild | None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return None
        try:
            check_cooldown(user_id=ctx.author.id, key="price", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return None
        if not self._is_staff(ctx.author):
            await ctx.send("❌ Staff only.", delete_after=5)
            await failed(ctx)
            return None
        return ctx.guild

    @commands.command(name="price")
    async def price(self, ctx: commands.Context) -> None:
        guild = await self._validate_ctx(ctx)
        if guild is None:
            return
        categories: List[str] = await self.item_serv.list_categories()
        if not categories:
            await ctx.send("⚠️ No item categories available.", delete_after=5)
            await failed(ctx)
            return
        for category in categories:
            items = await self.item_serv.list_item_price_by_category(category)
            embed = price_embed(category=category, items=items)
            await ctx.send(embed=embed, view=PriceRefreshView(category=category))
        await success(ctx)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Price(bot))
