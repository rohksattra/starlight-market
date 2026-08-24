"""Staff activity audit log (plain text, no pings)."""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from bot.activity_describe import (
    ActivityStatus,
    _finalize,
    describe_game_answer,
    describe_interaction,
    describe_prefix,
    format_log_message,
    person_name,
)
from core.tenant import GameContext, get_context

log = logging.getLogger("bot.activity_log")

_NO_MENTIONS = discord.AllowedMentions.none()
_SKIP_INTERACTION_TYPES = {
    discord.InteractionType.ping,
    discord.InteractionType.autocomplete,
}

async def log_activity(
    *,
    guild: discord.Guild | None,
    ctx: GameContext,
    member: discord.abc.User | discord.Member | None,
    action: str,
    status: ActivityStatus | None = None,
) -> None:
    channel_id = int(getattr(ctx.channels, "activity_log", 0) or 0)
    if guild is None or channel_id <= 0 or member is None:
        return

    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    action_text = _finalize(str(action or "").strip(), guild=guild)
    if not action_text:
        return

    text = format_log_message(member, action_text, status=status)
    try:
        await channel.send(text, allowed_mentions=_NO_MENTIONS)
    except discord.HTTPException:
        log.exception(
            "Failed to send activity log | guild=%s channel=%s",
            guild.id,
            channel_id,
        )


def schedule_activity(
    *,
    guild: discord.Guild | None,
    ctx: GameContext | None,
    member: discord.abc.User | discord.Member | None,
    action: str,
    status: ActivityStatus | None = None,
) -> None:
    if guild is None or ctx is None or member is None or getattr(member, "bot", False):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        log_activity(guild=guild, ctx=ctx, member=member, action=action, status=status),
        name="activity-log",
    )


def schedule_interaction(interaction: discord.Interaction) -> None:
    if interaction.type in _SKIP_INTERACTION_TYPES:
        return
    guild = interaction.guild
    if guild is None:
        return
    schedule_activity(
        guild=guild,
        ctx=get_context(guild.id),
        member=interaction.user,
        action=describe_interaction(interaction),
    )


def schedule_prefix(ctx: commands.Context) -> None:
    guild = ctx.guild
    if guild is None:
        return
    schedule_activity(
        guild=guild,
        ctx=get_context(guild.id),
        member=ctx.author,
        action=describe_prefix(ctx),
    )


def schedule_game_answer(
    *,
    message: discord.Message,
    ctx: GameContext,
    game_type: str,
    answer: str,
) -> None:
    guild = message.guild
    if guild is None:
        return
    schedule_activity(
        guild=guild,
        ctx=ctx,
        member=message.author,
        action=describe_game_answer(game_type, answer),
    )
