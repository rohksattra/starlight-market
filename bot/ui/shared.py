"""Shared embed helpers, footer, colors."""
from __future__ import annotations

from datetime import datetime

import discord

from core.tenant import GameContext, get_context
from core.time import utc_now

DEFAULT_BRAND_NAME = "Starlight Market"
DEFAULT_BRAND_EMOJI = "🌟"
DEFAULT_BRAND_LABEL = f"{DEFAULT_BRAND_EMOJI} {DEFAULT_BRAND_NAME}"

BUTTON_PRESS_NOTICE = (
    "💡 Bot may sometimes be a bit slow due to its hosting location. "
    "Please don't press the button too many times — just press once and wait."
)


def format_utc_timestamp(when: datetime | None = None) -> str:
    moment = when or utc_now()
    return f"{moment:%b %d, %Y} at {moment:%H:%M UTC}"


def market_brand_name(ctx: GameContext | None = None) -> str:
    if ctx is None:
        return DEFAULT_BRAND_NAME
    return ctx.brand.name


def market_brand_label(ctx: GameContext | None = None) -> str:
    if ctx is None:
        return DEFAULT_BRAND_LABEL
    return ctx.brand_label


def ctx_from_guild(guild: discord.Guild | None) -> GameContext | None:
    if guild is None:
        return None
    return get_context(guild.id)


def ctx_from_interaction(interaction: discord.Interaction) -> GameContext | None:
    return ctx_from_guild(interaction.guild)


def starlight_footer_text(
    *,
    ctx: GameContext | None = None,
    detail: str | None = None,
    include_button_notice: bool = True,
) -> str:
    brand = market_brand_label(ctx)
    head = brand if not detail else f"{brand} • {detail}"
    if not include_button_notice:
        return head
    return f"{head}\n{BUTTON_PRESS_NOTICE}"


def set_starlight_footer(
    embed: discord.Embed,
    *,
    ctx: GameContext | None = None,
    detail: str | None = None,
    include_button_notice: bool = True,
) -> discord.Embed:
    embed.set_footer(
        text=starlight_footer_text(
            ctx=ctx,
            detail=detail,
            include_button_notice=include_button_notice,
        )
    )
    return embed


def button_notice_content_suffix() -> str:
    return f"\n\n{BUTTON_PRESS_NOTICE}"
