from __future__ import annotations

import logging

import discord
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.uis.role_claim_embed import role_claim_embed
from app.uis.role_claim_view import RoleClaimView

log = logging.getLogger("cogs.role_claim")


class RoleClaim(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="roles")
    async def roles_command(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return
        if not has_any_role(ctx.author, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Only Bot Developer / Bank Manager.", delete_after=8)
            return
        channel = ctx.guild.get_channel(settings.ROLE_CLAIM_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            log.error("ROLE_CLAIM_CHANNEL_ID invalid | guild=%s", ctx.guild.id)
            await ctx.send("❌ Role claim channel is not configured correctly.", delete_after=8)
            return
        try:
            await channel.send(embed=role_claim_embed(), view=RoleClaimView())
        except discord.Forbidden:
            await ctx.send("❌ Cannot send messages to the role claim channel.", delete_after=8)
            return
        try:
            await ctx.message.add_reaction("✅")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleClaim(bot))
