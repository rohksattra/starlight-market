"""Staff activity audit log (plain text, no pings)."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import discord
from discord.ext import commands

from bot.ui.shared import format_utc_timestamp
from core.tenant import GameContext, get_context

log = logging.getLogger("bot.activity_log")

_NO_MENTIONS = discord.AllowedMentions.none()
_MAX_ACTION = 220
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
    "j": "Joined a giveaway",
    "p": "Viewed giveaway participants",
    "r": "Refreshed giveaway info",
    "c": "Cancelled a giveaway",
    "ra": "Rerolled all giveaway winners",
    "rp": "Rerolled some giveaway winners",
    "cl": "Marked giveaway prizes as claimed",
    "x": "Closed a giveaway",
}

_GAME_LABELS = {
    "counting": "counting",
    "wordchain": "word chain",
    "scramble": "scramble",
}

_BUTTON_LABEL_ACTIONS = {
    "start order": "Started creating an order",
    "claim": "Opened claim form on order",
    "unclaim": "Opened unclaim form on order",
    "refresh claims": "Refreshed order claim view",
    "close order": "Clicked Close Order button",
    "yes to close order": "Confirmed closing order (Yes)",
    "no to close order": "Cancelled closing order (No)",
    "refresh market stats": "Refreshed market stats",
    "✅ confirm": "Confirmed action",
    "❌ cancel": "Cancelled action",
}


def format_actor(member: discord.abc.User | discord.Member) -> str:
    display = getattr(member, "display_name", None) or member.name
    return f"{display} [@{member.name} | {member.id}]"


def format_log_message(
    member: discord.abc.User | discord.Member,
    action: str,
    *,
    when: datetime | None = None,
) -> str:
    action_text = _clip(str(action or "").strip())
    header = f"[{format_utc_timestamp(when)}] {format_actor(member)}"
    return _safe_code_block(f"{header}\n{action_text}")


def _clip(value: str, limit: int = _MAX_ACTION) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _safe_code_block(content: str) -> str:
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
            placeholder = getattr(child, "placeholder", None)
            if placeholder:
                return str(placeholder).strip() or None
    return None


def _humanize_custom_id(custom_id: str) -> str | None:
    cid = (custom_id or "").strip()
    if not cid:
        return None

    if cid == "order:entry:start":
        return _BUTTON_LABEL_ACTIONS["start order"]
    if cid == "orderclaim:claim":
        return _BUTTON_LABEL_ACTIONS["claim"]
    if cid == "orderclaim:unclaim":
        return _BUTTON_LABEL_ACTIONS["unclaim"]
    if cid == "orderclaim:refresh":
        return _BUTTON_LABEL_ACTIONS["refresh claims"]
    if cid == "orderclose:close":
        return _BUTTON_LABEL_ACTIONS["close order"]
    if cid == "orderclose:yes" or cid.startswith("orderclose:yes:"):
        return _BUTTON_LABEL_ACTIONS["yes to close order"]
    if cid == "orderclose:no" or cid.startswith("orderclose:no:"):
        return _BUTTON_LABEL_ACTIONS["no to close order"]
    if cid == "market_stat:refresh":
        return _BUTTON_LABEL_ACTIONS["refresh market stats"]

    if cid.startswith("rating:worker:"):
        stars = cid.rsplit(":", 1)[-1]
        return f"Rated worker {stars} star{'s' if stars != '1' else ''}"

    if cid.startswith("sl_rc:"):
        key = cid.split(":", 1)[1]
        role = _ROLE_CLAIM_LABELS.get(key, f"{key} role")
        return f"Toggled {role}"

    giveaway_match = re.fullmatch(r"sl_gv(?:w)?:[^:]+:([a-z]+)", cid)
    if giveaway_match:
        return _GIVEAWAY_ACTION_LABELS.get(giveaway_match.group(1), "Interacted with giveaway")

    game_match = re.fullmatch(r"game:([a-z]+):(attack|refresh)", cid)
    if game_match:
        game = _GAME_LABELS.get(game_match.group(1), game_match.group(1))
        if game_match.group(2) == "attack":
            return f"Attacked in {game} game"
        return f"Refreshed {game} game view"

    page_match = re.fullmatch(r"(.+):(prev|next|refresh)", cid)
    if page_match:
        target = page_match.group(1).replace(":", " / ")
        action = {
            "prev": "Viewed previous page",
            "next": "Viewed next page",
            "refresh": "Refreshed page",
        }[page_match.group(2)]
        return f"{action} ({target})"

    return None


def _action_from_button_label(label: str) -> str:
    key = label.strip().lower()
    return _BUTTON_LABEL_ACTIONS.get(key, f"Pressed {label.strip()} button")


def _component_action(interaction: discord.Interaction, custom_id: str) -> str:
    mapped = _humanize_custom_id(custom_id)
    if mapped:
        return mapped
    label = _label_from_message(interaction, custom_id)
    if label:
        return _action_from_button_label(label)
    return "Pressed a button"


def describe_interaction(interaction: discord.Interaction) -> str:
    data = interaction.data or {}
    itype = interaction.type

    if itype == discord.InteractionType.application_command:
        name = str(data.get("name") or "unknown")
        cmd_type = int(data.get("type") or 1)
        bits = _option_bits(data.get("options") if isinstance(data.get("options"), list) else None)
        suffix = f" ({', '.join(bits)})" if bits else ""
        if cmd_type in (2, 3):
            return _clip(f"Used context menu: {name}{suffix}")
        return _clip(f"Used /{name} command{suffix}")

    custom_id = str(data.get("custom_id") or "")
    if itype == discord.InteractionType.component:
        values = data.get("values")
        if isinstance(values, list) and values:
            picked = ", ".join(str(v) for v in values)
            menu = _label_from_message(interaction, custom_id)
            if menu:
                return _clip(f"Selected {picked} from {menu}")
            return _clip(f"Selected {picked} from menu")
        return _clip(_component_action(interaction, custom_id))

    if itype == discord.InteractionType.modal_submit:
        label = _label_from_message(interaction, custom_id) or custom_id or "form"
        if "quantity" in label.lower():
            return _clip("Submitted quantity form")
        return _clip(f"Submitted {label} form")

    return _clip("Used the bot")


def describe_prefix(ctx: commands.Context) -> str:
    content = (ctx.message.content or "").strip()
    if content:
        return _clip(f"Used command: {content}")
    name = ctx.command.qualified_name if ctx.command else "command"
    return _clip(f"Used !{name} command")


def describe_game_answer(game_type: str, answer: str) -> str:
    game = _GAME_LABELS.get(game_type, game_type)
    return _clip(f"Answered {game} game: {answer}")


async def log_activity(
    *,
    guild: discord.Guild | None,
    ctx: GameContext,
    member: discord.abc.User | discord.Member | None,
    action: str,
) -> None:
    channel_id = int(getattr(ctx.channels, "activity_log", 0) or 0)
    if guild is None or channel_id <= 0 or member is None:
        return

    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    action_text = _clip(str(action or "").strip())
    if not action_text:
        return

    text = format_log_message(member, action_text)
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
