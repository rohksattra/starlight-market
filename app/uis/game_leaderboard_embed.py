from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import discord

from app.domains.game_domain import GAME_TITLES, GAME_VALUE_LABELS, GameType
from app.uis.embed_footer import set_starlight_footer


def game_leaderboard_embed(
    *,
    game_type: GameType,
    entries: List[Dict[str, Any]],
    page: int,
    page_size: int,
    refreshed_at: datetime | None = None,
) -> discord.Embed:
    start = page * page_size
    end = start + page_size
    sliced = entries[start:end]

    label = GAME_VALUE_LABELS[game_type]
    lines: List[str] = []

    for idx, entry in enumerate(sliced, start=start + 1):
        name = entry.get("name", "Unknown")
        value = int(entry.get("value", 0))
        lines.append(f"***{idx}. {name}*** — ⭐ ***{value:,} {label}***")

    embed = discord.Embed(
        title=GAME_TITLES[game_type],
        description="\n".join(lines) if lines else "⚠️ No data available.",
        color=0xFFD700,
    )

    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    if refreshed_at is None:
        refreshed_at = datetime.utcnow()

    set_starlight_footer(
        embed,
        detail=(
            f"Page {page + 1}/{total_pages} • "
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        ),
    )
    return embed
