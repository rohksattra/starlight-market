from __future__ import annotations

import logging

import discord
from discord.ext import commands

from core.config import settings
from app.discord.tier_role_sync import schedule_member_tier_sync
from app.views.gateway_embed import farewell_embed, welcome_embed


log = logging.getLogger("events.member")


class MemberEvents(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        if guild is None:
            return

        schedule_member_tier_sync(guild, str(member.id))

        channel = guild.get_channel(settings.WELCOME_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            log.warning("Welcome channel invalid | guild=%s", guild.id)
            return
        try:
            await channel.send(embed=welcome_embed(member))
            log.debug("Member joined | user=%s guild=%s", member.id, guild.id)
        except discord.HTTPException:
            log.exception("Failed to send welcome embed | user=%s guild=%s", member.id, guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        guild = member.guild
        if guild is None:
            return
        channel = guild.get_channel(settings.FAREWELL_CHANNEL_ID)
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
