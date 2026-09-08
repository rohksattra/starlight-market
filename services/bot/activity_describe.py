"""Human-readable activity descriptions for the staff audit log."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Literal

import discord
from discord.ext import commands

from core.tenant import GameContext, get_context
from core.time import utc_now

log = logging.getLogger("bot.activity_log")
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
    "✅ confirm": "Confirmed the prompt",
    "❌ cancel": "Cancelled the prompt",
    "set quantity": "Opened payment quantity form",
    "calculate": "Calculated worker payment",
    "◀": "Viewed previous page of orders",
    "▶": "Viewed next page of orders",
    "🔄": "Refreshed the view",
}

_MODAL_ACTIONS = {
    "order:qty:place": "Submitted order quantity",
    "order:qty:claim": "Submitted claim quantity",
    "order:qty:unclaim": "Submitted unclaim quantity",
    "calc:qty": "Submitted payment quantity",
}

_SELECT_KINDS = {
    "order:select:category": ("category", "categories"),
    "order:select:item": ("item", "items"),
    "calc:select:order": ("order", "orders"),
    "calc:select:worker": ("worker", "workers"),
    "giveaway:select:winners": ("giveaway winner(s)", "giveaway winners"),
}

_LEADERBOARD_NAMES = {
    "worker": "workers leaderboard",
    "customer": "customers leaderboard",
    "item": "items leaderboard",
    "donor": "donors leaderboard",
    "rated": "rated workers leaderboard",
    "global": "points leaderboard",
}

_USER_OPTION_NAMES = {
    "user",
    "customer",
    "worker",
    "worker_id",
    "user_id",
    "customer_id",
    "host",
    "member",
    "target_user",
}
_ITEM_OPTION_NAMES = {"item", "item_id"}
_CHANNEL_OPTION_NAMES = {"channel", "channel_id"}
_OPTION_NAME_ALIASES = {
    "worker_id": "worker",
    "user_id": "user",
    "customer_id": "customer",
    "item_id": "item",
    "channel_id": "channel",
}

_SNOWFLAKE_RE = re.compile(r"(?<![\d,])\d{16,22}(?![\d,])")
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)
_OBJECTID_RE = re.compile(r"\b[0-9a-f]{24}\b", re.I)
_USER_MENTION_RE = re.compile(r"<@!?(\d{16,22})>")
_CHANNEL_MENTION_RE = re.compile(r"<#(\d{16,22})>")
_ROLE_MENTION_RE = re.compile(r"<@&(\d{16,22})>")
_FALLBACK_USER_RE = re.compile(r"User\s*\[[^\]]*\]")

ActivityStatus = Literal["success", "warning", "failed", "cancelled", "process"]

STATUS_EMOJI: dict[ActivityStatus, str] = {
    "success": "✅",
    "warning": "⚠️",
    "failed": "❌",
    "cancelled": "🚫",
    "process": "⏳",
}

_PROCESS_PREFIXES = (
    "started ",
    "opened ",
    "submitted ",
    "selected ",
    "viewed ",
    "used /",
    "used command",
    "used context",
    "used the bot",
    "clicked ",
    "pressed ",
    "confirmed ",
)


def format_timestamp(when: datetime | None = None) -> str:
    moment = when or utc_now()
    return moment.strftime("%d/%m/%Y %H:%M:%S")


def format_actor(member: discord.abc.User | discord.Member) -> str:
    display = getattr(member, "display_name", None) or member.name
    return f"{display} [@{member.name} | {member.id}]"


def format_log_message(
    member: discord.abc.User | discord.Member,
    action: str,
    *,
    when: datetime | None = None,
    status: ActivityStatus | None = None,
) -> str:
    action_text = _clip(str(action or "").strip())
    emoji = status_emoji(status, action_text)
    body = f"[{format_timestamp(when)}] {emoji}\n{format_actor(member)}\n{action_text}"
    return _safe_code_block(body)


def infer_activity_status(action: str) -> ActivityStatus:
    text = str(action or "").strip().lower()
    if not text:
        return "process"
    if any(word in text for word in ("cancelled", "canceled", "aborted")):
        return "cancelled"
    if text.startswith("failed") or " failed" in text:
        return "failed"
    if text.startswith("force ") or text.startswith("ran data cleanup") or text.startswith("rerolled"):
        return "warning"
    if text.startswith(_PROCESS_PREFIXES):
        return "process"
    return "success"


def status_emoji(status: ActivityStatus | None, action: str = "") -> str:
    resolved: ActivityStatus = status if status in STATUS_EMOJI else infer_activity_status(action)
    return STATUS_EMOJI[resolved]


def _clip(value: str, limit: int = _MAX_ACTION) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _looks_opaque_id(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if re.fullmatch(r"\d{16,22}", text):
        return True
    if _UUID_RE.fullmatch(text):
        return True
    if re.fullmatch(r"[0-9a-f]{24}", text, re.I):
        return True
    if re.fullmatch(r"[0-9a-f]{32}", text, re.I):
        return True
    return False


def person_name(guild: discord.Guild | None, user_id: object) -> str:
    text = str(user_id or "").strip()
    if guild is not None and text.isdigit():
        member = guild.get_member(int(text))
        if member is not None:
            return member.display_name
    if _looks_opaque_id(text):
        return "a member"
    return text or "a member"


def _channel_name(guild: discord.Guild | None, channel_id: object) -> str:
    text = str(channel_id or "").strip()
    if guild is not None and text.isdigit():
        channel = guild.get_channel(int(text))
        if channel is not None:
            return f"#{channel.name}"
    return "a channel"


def _role_name(guild: discord.Guild | None, role_id: object) -> str:
    text = str(role_id or "").strip()
    if guild is not None and text.isdigit():
        role = guild.get_role(int(text))
        if role is not None:
            return role.name
    return "a role"


def _sanitize_action(text: str, *, guild: discord.Guild | None = None) -> str:
    cleaned = str(text or "")
    cleaned = _USER_MENTION_RE.sub(lambda m: person_name(guild, m.group(1)), cleaned)
    cleaned = _CHANNEL_MENTION_RE.sub(lambda m: _channel_name(guild, m.group(1)), cleaned)
    cleaned = _ROLE_MENTION_RE.sub(lambda m: _role_name(guild, m.group(1)), cleaned)
    cleaned = _FALLBACK_USER_RE.sub("a member", cleaned)
    cleaned = _UUID_RE.sub("", cleaned)
    cleaned = _OBJECTID_RE.sub("", cleaned)
    cleaned = _SNOWFLAKE_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.:;])", r"\1", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\(\s*,", "(", cleaned)
    cleaned = re.sub(r",\s*\)", ")", cleaned)
    cleaned = re.sub(r"\s+in\s+(?=in\b)", " ", cleaned)
    return cleaned.strip()


def _finalize(value: str, *, guild: discord.Guild | None = None) -> str:
    return _clip(_sanitize_action(value, guild=guild))


def _safe_code_block(content: str) -> str:
    longest = max((len(m.group(0)) for m in re.finditer(r"`+", content)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{content}\n{fence}"


def _option_bits(options: list[dict] | None, interaction: discord.Interaction) -> list[str]:
    bits: list[str] = []
    for opt in options or []:
        name = str(opt.get("name", "")).strip()
        nested = opt.get("options")
        if nested:
            inner = " ".join(_option_bits(nested, interaction))
            bits.append(f"{name} {inner}".strip() if name else inner)
            continue
        if "value" not in opt or not name:
            continue
        friendly = _friendly_option_value(interaction, name, opt["value"])
        if friendly is None:
            continue
        bits.append(f"{_OPTION_NAME_ALIASES.get(name, name)}={friendly}")
    return bits


def _friendly_option_value(interaction: discord.Interaction, name: str, value: object) -> str | None:
    text = str(value).strip()
    key = name.lower()
    if key in _USER_OPTION_NAMES:
        return person_name(interaction.guild, text)
    if key in _CHANNEL_OPTION_NAMES:
        label = _channel_name(interaction.guild, text)
        return None if label == "a channel" and _looks_opaque_id(text) else label
    if key in _ITEM_OPTION_NAMES and _looks_opaque_id(text):
        return None
    if _looks_opaque_id(text):
        return None
    return text


def _component_custom_id(node) -> str:
    if isinstance(node, dict):
        return str(node.get("custom_id") or "")
    return str(getattr(node, "custom_id", "") or "")


def _component_text(node) -> str | None:
    if isinstance(node, dict):
        for key in ("label", "placeholder"):
            value = str(node.get(key) or "").strip()
            if value:
                return value
        return None
    for key in ("label", "placeholder"):
        value = str(getattr(node, key, "") or "").strip()
        if value:
            return value
    return None


def _label_from_message(interaction: discord.Interaction, custom_id: str) -> str | None:
    message = interaction.message
    if message is None or not custom_id:
        return None
    rows = getattr(message, "components", None)
    for child in _walk_components(list(rows) if rows else None):
        if _component_custom_id(child) != custom_id:
            continue
        return _component_text(child)
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
    if cid == "order:confirm":
        return "Confirmed new order"
    if cid == "order:cancel":
        return "Cancelled new order"
    if cid == "calc:qty:open":
        return _BUTTON_LABEL_ACTIONS["set quantity"]
    if cid == "calc:submit":
        return _BUTTON_LABEL_ACTIONS["calculate"]
    if cid == "calc:page:prev":
        return _BUTTON_LABEL_ACTIONS["◀"]
    if cid == "calc:page:next":
        return _BUTTON_LABEL_ACTIONS["▶"]
    if cid == "prompt:confirm":
        return _BUTTON_LABEL_ACTIONS["✅ confirm"]
    if cid == "prompt:cancel":
        return _BUTTON_LABEL_ACTIONS["❌ cancel"]

    if cid.startswith("rating:worker:"):
        stars = cid.rsplit(":", 1)[-1]
        return f"Clicked worker rating button ({stars} star{'s' if stars != '1' else ''})"

    if cid.startswith("sl_rc:"):
        key = cid.split(":", 1)[1]
        if _looks_opaque_id(key):
            return "Toggled a role"
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
        target = _page_target_label(page_match.group(1))
        action = {
            "prev": "Viewed previous page",
            "next": "Viewed next page",
            "refresh": "Refreshed",
        }[page_match.group(2)]
        if page_match.group(2) == "refresh":
            return f"{action} {target}"
        return f"{action} of {target}"

    return None


def _page_target_label(raw: str) -> str:
    target = (raw or "").strip()
    if target.startswith("price:"):
        category = target.split(":", 1)[1].strip()
        return f"{category} prices" if category else "prices"
    if target == "claimable":
        return "claimable items"
    if target.startswith("leaderboard:"):
        kind = target.split(":", 1)[1].strip()
        return _LEADERBOARD_NAMES.get(kind, "leaderboard")
    if target.startswith("game_leaderboard:"):
        game = target.split(":", 1)[1].strip()
        return f"{_GAME_LABELS.get(game, game)} leaderboard"
    if _looks_opaque_id(target) or _SNOWFLAKE_RE.search(target) or _UUID_RE.search(target):
        return "the list"
    cleaned = target.replace(":", " ").strip()
    return cleaned or "the list"


def _action_from_button_label(label: str) -> str:
    key = label.strip().lower()
    mapped = _BUTTON_LABEL_ACTIONS.get(key)
    if mapped:
        return mapped
    if _looks_opaque_id(label.strip()) or _UUID_RE.search(label) or _SNOWFLAKE_RE.search(label):
        return "Pressed a button"
    return f"Pressed {label.strip()} button"


def _walk_components(nodes: list | None):
    for node in nodes or []:
        if isinstance(node, dict):
            nested = node.get("components")
            if nested:
                yield from _walk_components(nested)
                continue
            yield node
            continue
        children = getattr(node, "children", None)
        if children:
            yield from _walk_components(list(children))
            continue
        yield node


def _option_label(opt) -> tuple[str, str]:
    if isinstance(opt, dict):
        value = str(opt.get("value") or "")
        label = str(opt.get("label") or "").strip()
        return value, label or value
    value = str(getattr(opt, "value", "") or "")
    label = str(getattr(opt, "label", "") or "").strip()
    return value, label or value


def _select_option_labels(interaction: discord.Interaction, custom_id: str, values: list[str]) -> list[str]:
    wanted = {str(v) for v in values}
    found: dict[str, str] = {}
    message = interaction.message
    rows = getattr(message, "components", None) if message is not None else None
    for child in _walk_components(list(rows) if rows else None):
        child_id = _component_custom_id(child)
        if custom_id and child_id and child_id != custom_id:
            continue
        options = getattr(child, "options", None)
        if options is None and isinstance(child, dict):
            options = child.get("options")
        for opt in options or []:
            value, label = _option_label(opt)
            if value in wanted:
                found[value] = label
    return [found.get(str(v), str(v)) for v in values]


def _is_quantity_value(raw: str) -> bool:
    text = str(raw or "").strip().replace(",", "").replace("_", "")
    return bool(text) and text.isdigit()


def _format_quantity(raw: str) -> str:
    text = raw.strip().replace(",", "").replace("_", "")
    try:
        return f"{int(text):,}"
    except ValueError:
        return raw.strip()


def _modal_fields(data: dict) -> dict[str, str]:
    fields: dict[str, str] = {}
    nested = data.get("components") if isinstance(data.get("components"), list) else None
    for node in _walk_components(nested):
        if isinstance(node, dict):
            if "value" not in node:
                continue
            key = str(node.get("custom_id") or "field").strip() or "field"
            fields[key] = str(node.get("value") or "")
            continue
        if getattr(node, "value", None) is None:
            continue
        key = str(getattr(node, "custom_id", "") or "field").strip() or "field"
        fields[key] = str(getattr(node, "value") or "")
    return fields


def _describe_modal(custom_id: str, data: dict) -> str:
    fields = _modal_fields(data)
    quantity = fields.get("quantity") or ""
    if not _is_quantity_value(quantity) and len(fields) == 1:
        only = next(iter(fields.values()), "")
        if _is_quantity_value(only):
            quantity = only
        else:
            quantity = ""
    mapped = _MODAL_ACTIONS.get(custom_id)
    if mapped:
        if _is_quantity_value(quantity):
            return f"{mapped}: {_format_quantity(quantity)}x"
        return mapped
    cid = custom_id.lower()
    if _is_quantity_value(quantity) and ("qty" in cid or "quantity" in cid or "quantity" in fields or len(fields) == 1):
        return f"Submitted quantity: {_format_quantity(quantity)}x"
    if fields:
        bits: list[str] = []
        for name, value in fields.items():
            if not value or _looks_opaque_id(name):
                continue
            if _looks_opaque_id(value) or _UUID_RE.search(value) or _SNOWFLAKE_RE.search(value):
                continue
            bits.append(f"{name}={value}")
        return f"Submitted form ({', '.join(bits)})" if bits else "Submitted a form"
    return "Submitted a form"


def _select_kind(custom_id: str, menu: str) -> tuple[str, str] | None:
    mapped = _SELECT_KINDS.get(custom_id)
    if mapped:
        return mapped
    menu_l = menu.lower()
    if "categor" in menu_l:
        return "category", "categories"
    if "item" in menu_l:
        return "item", "items"
    if "order" in menu_l:
        return "order", "orders"
    if "worker" in menu_l:
        return "worker", "workers"
    if "winner" in menu_l:
        return "giveaway winner(s)", "giveaway winners"
    return None


def _describe_select(interaction: discord.Interaction, custom_id: str, values: list[str]) -> str:
    labels = _select_option_labels(interaction, custom_id, values)
    menu = (_label_from_message(interaction, custom_id) or "").strip()
    kind = _select_kind(custom_id, menu)
    noun, plural = kind if kind else ("option", "list")
    raw_values = {str(v) for v in values}

    if raw_values == {"__more__"} or labels == ["➡️ More..."]:
        return f"Viewed next page of {plural}"
    if raw_values == {"__prev__"} or labels == ["⬅️ Previous..."]:
        return f"Viewed previous page of {plural}"
    if raw_values <= {"__none__", "__placeholder__"}:
        return f"Opened {plural} menu"

    resolved_labels = [
        label
        for label in labels
        if label
        and label != "➡️ More..."
        and label != "⬅️ Previous..."
        and not _looks_opaque_id(label)
        and not _UUID_RE.search(label)
        and not _SNOWFLAKE_RE.search(label)
    ]
    if not resolved_labels:
        return f"Selected {noun}"

    picked = ", ".join(resolved_labels)
    if kind:
        return f"Selected {noun}: {picked}"
    if menu and not _looks_opaque_id(menu) and not _SNOWFLAKE_RE.search(menu):
        return f"Selected {picked} from {menu}"
    return f"Selected {noun}: {picked}"


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
        bits = _option_bits(
            data.get("options") if isinstance(data.get("options"), list) else None,
            interaction,
        )
        suffix = f" ({', '.join(bits)})" if bits else ""
        if cmd_type in (2, 3):
            return _finalize(f"Used context menu: {name}{suffix}", guild=interaction.guild)
        return _finalize(f"Used /{name} command{suffix}", guild=interaction.guild)

    custom_id = str(data.get("custom_id") or "")
    if itype == discord.InteractionType.component:
        values = data.get("values")
        if isinstance(values, list) and values:
            return _finalize(
                _describe_select(interaction, custom_id, [str(v) for v in values]),
                guild=interaction.guild,
            )
        return _finalize(_component_action(interaction, custom_id), guild=interaction.guild)

    if itype == discord.InteractionType.modal_submit:
        return _finalize(
            _describe_modal(custom_id, data if isinstance(data, dict) else {}),
            guild=interaction.guild,
        )

    return _finalize("Used the bot", guild=interaction.guild)


def describe_prefix(ctx: commands.Context) -> str:
    content = (ctx.message.content or "").strip()
    if content:
        return _finalize(f"Used command: {content}", guild=ctx.guild)
    name = ctx.command.qualified_name if ctx.command else "command"
    return _finalize(f"Used !{name} command", guild=ctx.guild)


def describe_game_answer(game_type: str, answer: str) -> str:
    game = _GAME_LABELS.get(game_type, game_type)
    return _clip(f"Answered {game} game: {answer}")

