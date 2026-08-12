"""Staff/dev activity audit log (plain text, no pings).

Captures every member interaction with the bot: slash, prefix, buttons,
selects, modals, context menus, and typed mini-game answers.
"""
from __future__ import annotations

import asyncio
import logging
import re

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

_ROLE_CLAIM_LABELS = {
    "worker": "Worker role",
    "customer": "Customer role",
    "announce": "Announcements role",
    "giveaway": "Giveaway role",
    "content": "Content role",
}

_GIVEAWAY_ACTION_LABELS = {
    "j": "join giveaway",
    "p": "view giveaway participants",
    "r": "refresh giveaway",
    "c": "cancel giveaway",
    "ra": "reroll all giveaway winners",
    "rp": "reroll some giveaway winners",
    "cl": "mark giveaway prizes claimed",
    "x": "close giveaway",
}

_GAME_LABELS = {
    "counting": "counting",
    "wordchain": "word chain",
    "scramble": "scramble",
}


def format_actor(member: discord.abc.User | discord.Member) -> str:
    display = getattr(member, "display_name", None) or member.name
    return f"[{display}][{member.name}][{member.id}]"


def _clip(value: str, limit: int = _MAX_ACTION) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _safe_code_block(content: str) -> str:
    """Wrap text in a Discord code block without breaking on backticks inside."""
    # Fence length must exceed any run of backticks in the body.
    longest = max((len(m.group(0)) for m in re.finditer(r"`+", content)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{content}\n{fence}"


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


def _label_from_message(interaction: discord.Interaction, custom_id: str) -> str | None:
    message = interaction.message
    if message is None or not custom_id:
        return None
    for row in getattr(message, "components", None) or []:
        for child in getattr(row, "children", None) or []:
            if str(getattr(child, "custom_id", "") or "") != custom_id:
                continue
            label = getattr(child, "label", None)
            if label:
                return str(label).strip() or None
    return None


def _humanize_custom_id(custom_id: str) -> str | None:
    cid = (custom_id or "").strip()
    if not cid:
        return None

    if cid == "order:entry:start":
        return "Start Order"
    if cid == "orderclaim:claim":
        return "Claim"
    if cid == "orderclaim:unclaim":
        return "Unclaim"
    if cid == "orderclaim:refresh":
        return "Refresh Claims"
    if cid == "orderclose:close":
        return "Close Order"
    if cid == "orderclose:yes" or cid.startswith("orderclose:yes:"):
        return "Yes to close order"
    if cid == "orderclose:no" or cid.startswith("orderclose:no:"):
        return "No to close order"
    if cid == "market_stat:refresh":
        return "Refresh Market Stats"

    if cid.startswith("rating:worker:"):
        stars = cid.rsplit(":", 1)[-1]
        return f"Rate Worker ({stars} star{'s' if stars != '1' else ''})"

    if cid.startswith("sl_rc:"):
        key = cid.split(":", 1)[1]
        return _ROLE_CLAIM_LABELS.get(key, f"{key} role")

    giveaway_match = re.fullmatch(r"sl_gv(?:w)?:[^:]+:([a-z]+)", cid)
    if giveaway_match:
        return _GIVEAWAY_ACTION_LABELS.get(giveaway_match.group(1), "giveaway action")

    game_match = re.fullmatch(r"game:([a-z]+):(attack|refresh)", cid)
    if game_match:
        game = _GAME_LABELS.get(game_match.group(1), game_match.group(1))
        action = "attack" if game_match.group(2) == "attack" else "refresh"
        return f"{action} {game} game"

    page_match = re.fullmatch(r"(.+):(prev|next|refresh)", cid)
    if page_match:
        target = page_match.group(1).replace(":", " / ")
        action = {"prev": "previous page", "next": "next page", "refresh": "refresh"}[
            page_match.group(2)
        ]
        return f"{action} ({target})"

    return None


def _component_label(interaction: discord.Interaction, custom_id: str) -> str:
    return (
        _humanize_custom_id(custom_id)
        or _label_from_message(interaction, custom_id)
        or "a button"
    )


def describe_interaction(interaction: discord.Interaction) -> str:
    data = interaction.data or {}
    itype = interaction.type

    if itype == discord.InteractionType.application_command:
        name = str(data.get("name") or "unknown")
        cmd_type = int(data.get("type") or 1)
        bits = _option_bits(data.get("options") if isinstance(data.get("options"), list) else None)
        suffix = f" ({', '.join(bits)})" if bits else ""
        if cmd_type in (2, 3):
            return _clip(f"used context menu {name}{suffix}")
        return _clip(f"ran /{name}{suffix}")

    custom_id = str(data.get("custom_id") or "")
    label = _component_label(interaction, custom_id)
    if itype == discord.InteractionType.component:
        values = data.get("values")
        if isinstance(values, list) and values:
            picked = ", ".join(str(v) for v in values)
            return _clip(f"chose {picked} from {label}")
        return _clip(f"pressed {label}")

    if itype == discord.InteractionType.modal_submit:
        return _clip(f"submitted form ({label})")

    return _clip(f"used bot interaction ({itype})")


def describe_prefix(ctx: commands.Context) -> str:
    content = (ctx.message.content or "").strip()
    if content:
        return _clip(f"ran {content}")
    name = ctx.command.qualified_name if ctx.command else "command"
    return _clip(f"ran !{name}")


def describe_game_answer(game_type: str, answer: str) -> str:
    game = _GAME_LABELS.get(game_type, game_type)
    return _clip(f"answered {game} with {answer}")


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

    text = _safe_code_block(f"{format_actor(member)} {action_text}")
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
