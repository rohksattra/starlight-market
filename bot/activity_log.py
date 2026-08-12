"""Staff/dev activity audit log (plain text, no pings).

Captures every member interaction with the bot: slash, prefix, buttons,
selects, modals, context menus, and typed mini-game answers.
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from core.tenant import GameContext, get_context

log = logging.getLogger("bot.activity_log")

_NO_MENTIONS = discord.AllowedMentions.none()
_MAX_ACTION = 180
_SKIP_INTERACTION_TYPES = {
    discord.InteractionType.ping,
    discord.InteractionType.autocomplete,
}


def format_actor(member: discord.abc.User | discord.Member) -> str:
    display = getattr(member, "display_name", None) or member.name
    return f"[{display}][{member.name}][{member.id}]"


def _clip(value: str, limit: int = _MAX_ACTION) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _option_bits(options: list[dict] | None) -> list[str]:
    bits: list[str] = []
    for opt in options or []:
        name = str(opt.get("name", "")).strip()
        nested = opt.get("options")
        if nested:
            inner = " ".join(_option_bits(nested))
            bits.append(f"{name} {inner}".strip() if name else inner)
            continue
        if "value" in opt and name:
            bits.append(f"{name}={opt['value']}")
    return bits


def describe_interaction(interaction: discord.Interaction) -> str:
    data = interaction.data or {}
    itype = interaction.type

    if itype == discord.InteractionType.application_command:
        name = str(data.get("name") or "unknown")
        cmd_type = int(data.get("type") or 1)
        bits = _option_bits(data.get("options") if isinstance(data.get("options"), list) else None)
        suffix = f" {' '.join(bits)}" if bits else ""
        if cmd_type in (2, 3):
            return _clip(f"used context menu {name}{suffix}")
        return _clip(f"used /{name}{suffix}")

    custom_id = str(data.get("custom_id") or "")
    if itype == discord.InteractionType.component:
        values = data.get("values")
        if isinstance(values, list) and values:
            picked = ", ".join(str(v) for v in values)
            return _clip(f"selected `{custom_id}` ({picked})")
        return _clip(f"clicked `{custom_id}`")

    if itype == discord.InteractionType.modal_submit:
        return _clip(f"submitted modal `{custom_id}`")

    return _clip(f"used interaction type={itype}")


def describe_prefix(ctx: commands.Context) -> str:
    content = (ctx.message.content or "").strip()
    if content:
        return _clip(f"used {content}")
    name = ctx.command.qualified_name if ctx.command else "command"
    return _clip(f"used !{name}")


def describe_game_answer(game_type: str, answer: str) -> str:
    return _clip(f"answered {game_type} {answer}")


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

    action_text = _clip(str(action or "").strip())
    if not action_text:
        return

    text = f"```{format_actor(member)} {action_text}```"
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
) -> None:
    if guild is None or ctx is None or member is None or getattr(member, "bot", False):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        log_activity(guild=guild, ctx=ctx, member=member, action=action),
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
