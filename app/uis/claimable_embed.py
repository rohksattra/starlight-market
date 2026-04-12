#app/uis/claimable_embed.py
from __future__ import annotations

from typing import List, Dict, Any
import discord
from datetime import datetime


def claimable_embed(
    *,
    entries: List[Dict[str, Any]],
    page: int,
    page_size: int,
    refreshed_at: datetime | None = None,
) -> discord.Embed:

    start = page * page_size
    end = start + page_size
    sliced = entries[start:end]

    lines = []
    for idx, e in enumerate(sliced, start=start + 1):
        ch = f"<#{e['channel_id']}>" if e.get("channel_id") else "No Channel"

        name = e.get("name", "Unknown")
        item_name = name.split("•")[-1].strip()
        emoji = e.get("item_emoji", "") or "🌟"

        qty = int(e.get("value", 0))

        lines.append(
            f"***{idx}. {emoji} {item_name} — 🏷 {qty:,}***\n"
            f"{ch}"
        )

    embed = discord.Embed(
        title="📦 Claimable Orders",
        description="\n".join(lines) if lines else "⚠️ No claimable orders.",
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
