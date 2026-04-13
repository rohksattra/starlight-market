from __future__ import annotations

from typing import Dict, Any, List
from datetime import datetime

import discord


def price_embed(*, category: str, items: List[Dict[str, Any]], refreshed_at: datetime | None = None,
) -> discord.Embed:

    lines: List[str] = []

    for item in items:
        emoji = item.get("item_emoji") or "🌟"
        name = item.get("item_name", "Unknown Item")
        price = int(item.get("item_price", 0))

        lines.append(f"***{emoji} {name}*** — 🪙 ***{price:,}***")

    embed = discord.Embed(
        title=f"📦 Price List Each— ***{category}***",
        description="\n".join(lines) if lines else "⚠️ No items available.",
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