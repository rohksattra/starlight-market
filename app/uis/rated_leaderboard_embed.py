from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import discord


def rated_leaderboard_embed(
    *,
    title: str,
    entries: List[Dict[str, Any]],
    page: int,
    page_size: int,
    refreshed_at: datetime | None = None,
) -> discord.Embed:
    start = page * page_size
    end = start + page_size
    sliced = entries[start:end]

    lines: List[str] = []
    for idx, entry in enumerate(sliced, start=start + 1):
        name = entry.get("name", "Unknown User")
        avg = float(entry.get("avg", 0))
        count = int(entry.get("count", 0))
        lines.append(f"***{idx}. {name}*** — ⭐ ***{avg:.2f}*** (*{count:,} rating(s)*)")

    embed = discord.Embed(
        title=title,
        description="\n".join(lines) if lines else "⚠️ No data available.",
        color=0xFFD700,
    )

    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    if refreshed_at is None:
        refreshed_at = datetime.utcnow()

    embed.set_footer(
        text=(
            "🌟 Starlight Market • "
            f"Page {page + 1}/{total_pages} • "
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        )
    )
    return embed

