from __future__ import annotations

from typing import Dict, Any, List
from datetime import datetime

import discord

from app.views.embed_footer import set_starlight_footer


PAGE_SIZE = 25


def price_embed(*, category: str, items: List[Dict[str, Any]], page: int, page_size: int = PAGE_SIZE, refreshed_at: datetime | None = None) -> discord.Embed:
    start = page * page_size
    end = start + page_size
    sliced = items[start:end]

    lines: List[str] = []

    for item in sliced:
        emoji = item.get("item_emoji") or "🌟"
        name = item.get("item_name", "Unknown Item")
        price = int(item.get("item_price", 0))

        lines.append(f"***{emoji} {name}*** — 🪙 ***{price:,}***")

    embed = discord.Embed(
        title=f"📦 Price List — ***{category}***",
        description="\n".join(lines) if lines else "⚠️ No items available.",
        color=0xFFD700,
    )

    total_pages = max(1, (len(items) + page_size - 1) // page_size)

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