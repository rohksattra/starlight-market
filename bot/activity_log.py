"""Staff/dev market activity audit log (plain text, no pings)."""
from __future__ import annotations

import logging

import discord

from core.tenant import GameContext

log = logging.getLogger("bot.activity_log")

_NO_MENTIONS = discord.AllowedMentions.none()


def format_actor(member: discord.abc.User | discord.Member) -> str:
    display = getattr(member, "display_name", None) or member.name
    return f"```[{display}][{member.name}][{member.id}]```"


async def log_activity(
    *,
    guild: discord.Guild | None,
    ctx: GameContext,
    member: discord.abc.User | discord.Member | None,
    action: str,
) -> None:
    """
    Send a market activity line to channels.activity_log.
    No-op when channel id is 0 / missing / send fails.
    """
    channel_id = int(getattr(ctx.channels, "activity_log", 0) or 0)
    if guild is None or channel_id <= 0 or member is None:
        return

    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    text = f"{format_actor(member)} {action}".strip()
    if not text:
        return

    try:
        await channel.send(text, allowed_mentions=_NO_MENTIONS)
    except discord.HTTPException:
        log.exception(
            "Failed to send activity log | guild=%s channel=%s",
            guild.id,
            channel_id,
        )
