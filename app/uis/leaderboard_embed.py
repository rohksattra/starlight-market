# app/uis/leaderboard_embed.py
from __future__ import annotations

from typing import List, Dict, Any, Literal
from datetime import datetime

import discord


LBType = Literal["worker", "customer", "item"]


def leaderboard_embed(*, title: str, entries: List[Dict[str, Any]], lb_type: LBType, refreshed_at: datetime | None = None) -> discord.Embed:
    lines: List[str] = []
    for idx, entry in enumerate(entries, start=1):
        value = int(entry.get("value", 0))
        if lb_type == "item":
            name = str(entry.get("name", "Unknown Item"))
            lines.append(f"***{idx}. {name}*** — 🏷 ***{value:,}x***")
        else:
            name = entry.get("name", "Unknown User")
            lines.append(f"***{idx}. {name}*** — 🪙 ***{value:,}***")
    embed = discord.Embed(
        title=title,
        description="\n".join(lines) if lines else "⚠️ No data available.",
        color=0xFFD700,
    )
    if refreshed_at is None:
        refreshed_at = datetime.utcnow()
    embed.set_footer(text=(
            "🌟 Starlight Market • "
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        ))
    return embed
