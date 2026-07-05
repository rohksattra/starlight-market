from __future__ import annotations

from typing import Any, Dict, List, Sequence
from datetime import datetime

import discord

from app.views.embed_footer import set_starlight_footer


def market_statistic_embed(
    *, guild: discord.Guild, order: Dict[str, int], gold: Dict[str, int],
    leaderboard: Dict[str, Sequence[Dict[str, Any]]],
    total_workers: int, total_customers: int,
    refreshed_at: datetime | None = None
) -> discord.Embed:

    if not order or not gold:
        embed = discord.Embed(
            title="📊 Starlight Market Statistics",
            description="⚠️ **No data available.**",
            color=0xFFD700,
        )
        set_starlight_footer(embed)
        return embed

    completed = order.get("completed", 0)

    embed = discord.Embed(
        title="📊 Starlight Market Statistics",
        color=0xFFD700,
    )

    embed.description = (
        "### 🛒 Order Overview\n"
        f"- Total Orders: 🛒 ***{order.get('total', 0):,}***\n"
        f"- Active Orders: 🔄 ***{order.get('active', 0):,}***\n"
        f"- Completed Orders: ✅ ***{completed:,}***\n"
        f"- Finished Orders: 📦 ***{order.get('finished', 0):,}***\n"
        f"- Canceled Orders: ❌ ***{order.get('canceled', 0):,}***\n\n"
        "### 👥 Market Overview\n"
        f"- Total Workers: 👷 ***{total_workers:,}***\n"
        f"- Total Customers: 🛍️ ***{total_customers:,}***\n\n"
        "### 🪙 Gold Overview\n"
        f"- Workers Income: 🪙 ***{gold.get('worker_income', 0):,}***\n"
        f"- Customers Spent: 🪙 ***{gold.get('customer_spent', 0):,}***\n\n"
        "### 🥇 Leaderboard\n"
        "**Top 5 Workers**\n"
        f"{_fmt_users(guild, leaderboard.get('workers', []))}\n\n"
        "**Top 5 Customers**\n"
        f"{_fmt_users(guild, leaderboard.get('customers', []))}\n\n"
        "**Top 5 Items**\n"
        f"{_fmt_items(leaderboard.get('items', []))}"
    )

    if refreshed_at is None:
        refreshed_at = datetime.utcnow()

    set_starlight_footer(
        embed,
        detail=(
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        ),
    )

    return embed


def _fmt_users(guild: discord.Guild, rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return "- No data"

    lines: List[str] = []

    for i, row in enumerate(rows, start=1):
        user_id = row.get("id")
        value = int(row.get("value", 0))

        if not user_id:
            name = "Unknown User"
        else:
            member = guild.get_member(int(user_id))
            name = member.display_name if member else "Unknown"

        lines.append(f"{i}. ***{name}*** — 🪙 ***{value:,}***")

    return "\n".join(lines)


def _fmt_items(rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return "- No data"

    lines: List[str] = []

    for i, row in enumerate(rows, start=1):
        name = row.get("name", "Unknown")
        emoji = row.get("item_emoji") or "🌟"
        value = int(row.get("value", 0))

        lines.append(f"{i}. ***{emoji} {name}*** — 🏷 ***{value:,}x***")

    return "\n".join(lines)