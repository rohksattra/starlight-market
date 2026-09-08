"""Grind estimate embed (price-list style)."""
from __future__ import annotations

import discord

from bot.ui.shared import set_starlight_footer
from core.tenant import GameContext
from services.monster_grind import (
    FALLBACK_EMOJI,
    GrindEstimate,
    format_chance_denom,
    format_qty_range,
)
from utils.assets import monster_image_url

EMBED_COLOR = 0xFFD700
MAX_DESCRIPTION = 4096
DISCLAIMER = (
    "*Drops are RNG-based. Numbers shown are statistical averages, not guarantees.*"
)


def grind_estimate_embed(
    estimate: GrindEstimate,
    *,
    ctx: GameContext | None = None,
) -> discord.Embed:
    emoji = estimate.monster_emoji.strip() or FALLBACK_EMOJI
    header = (
        f"From ***{estimate.kill_count:,}*** kills of {emoji} "
        f"***{estimate.monster_name}*** (Lv {estimate.monster_level}):\n\n"
        f"🟡 EXP ***{estimate.total_exp:,}*** · 🪙 Gold ***{estimate.total_gold:,}***"
    )

    if estimate.drops:
        drop_lines = [
            (
                f"***{(drop.emoji or '').strip() or FALLBACK_EMOJI} {drop.name}*** "
                f"({format_chance_denom(drop.chance_denom)}) "
                f"— ***{format_qty_range(drop.expected_min, drop.expected_max)}***"
            )
            for drop in estimate.drops
        ]
    else:
        drop_lines = ["⚠️ No drop data."]

    description = _join_description(header, drop_lines, extra_notes=_bottom_notes(estimate))
    embed = discord.Embed(
        title=f"⚔️ Grind Estimate — ***{estimate.monster_name}***",
        description=description,
        color=EMBED_COLOR,
    )
    if ctx is not None and estimate.monster_image:
        thumb = monster_image_url(ctx, monster_image=estimate.monster_image)
        if thumb:
            embed.set_thumbnail(url=thumb)
    return set_starlight_footer(
        embed,
        ctx=ctx,
        detail="Grind Estimate",
        include_button_notice=False,
    )


def _bottom_notes(estimate: GrindEstimate) -> list[str]:
    notes: list[str] = []
    if estimate.drop_rolls > 1:
        note = estimate.monster_drop_note or f"Drops {estimate.drop_rolls} items upon death"
        notes.append(f"*{note.rstrip('.')}.*")
        notes.append(f"*Estimates are multiplied by {estimate.drop_rolls}.*")
    elif estimate.monster_drop_note:
        notes.append(f"*{estimate.monster_drop_note}*")
    return notes


def _join_description(
    header: str,
    drop_lines: list[str],
    extra_notes: list[str] | None = None,
) -> str:
    extra = list(extra_notes or [])
    if extra:
        suffix = "\n\n" + "\n".join(extra) + "\n\n" + DISCLAIMER
    else:
        suffix = "\n\n" + DISCLAIMER
    lines = list(drop_lines)
    hidden = 0
    while True:
        more = f"\n*…and {hidden} more.*" if hidden else ""
        body = "\n".join(lines) if lines else "⚠️ No drop data."
        text = f"{header}\n\n{body}{more}{suffix}"
        if len(text) <= MAX_DESCRIPTION:
            return text
        if not lines:
            return text[:MAX_DESCRIPTION]
        lines.pop()
        hidden += 1
