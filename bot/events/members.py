"""Discord event listeners for member join/leave."""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.tier_sync import schedule_member_tier_sync
from bot.ui.community import farewell_embed, welcome_embed
from core.tenant import get_context

log = logging.getLogger("bot.events.members")


class MemberEvents(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        if guild is None:
            return

        ctx = get_context(guild.id)
        if ctx is None:
            return

        schedule_member_tier_sync(guild, str(member.id), ctx)

        channel = guild.get_channel(ctx.channels.welcome)
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            await channel.send(embed=welcome_embed(member))
        except discord.HTTPException:
            log.exception("Failed to send welcome embed | user=%s guild=%s", member.id, guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        guild = member.guild
        if guild is None:
            return

        ctx = get_context(guild.id)
        if ctx is None:
            return

        channel = guild.get_channel(ctx.channels.farewell)
        if not isinstance(channel, discord.TextChannel):
            log.warning("Farewell channel invalid | guild=%s", guild.id)
            return

        try:
            await channel.send(embed=farewell_embed(member))
            log.debug("Member left | user=%s guild=%s", member.id, guild.id)
        except discord.HTTPException:
            log.exception("Failed to send farewell embed | user=%s guild=%s", member.id, guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MemberEvents(bot))
