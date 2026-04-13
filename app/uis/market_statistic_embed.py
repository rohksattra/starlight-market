# app/uis/market_statistic_embed.py
from __future__ import annotations

from typing import Any, Dict, List, Sequence

import discord


def market_statistic_embed(
    *, guild: discord.Guild, order: Dict[str, int], gold: Dict[str, int],
    leaderboard: Dict[str, Sequence[Dict[str, Any]]],
    total_workers: int, total_customers: int,
) -> discord.Embed:

    if not order or not gold:
        embed = discord.Embed(
            title="📊 Starlight Market Statistics",
            description="⚠️ **No data available.**",
            color=0xFFD700,
        )
        embed.set_footer(text="🌟 Starlight Market")
        return embed

    completed = order.get("completed", 0)

    embed = discord.Embed(
        title="📊 Starlight Market Statistics",
        color=0xFFD700,
    )

    embed.description = (
        "### 🛒 Order Overview\n"
        f"- Total Orders: 🛒 ***{order['total']:,}***\n"
        f"- Active Orders: 🔄 ***{order['active']:,}***\n"
        f"- Completed Orders: ✅ ***{completed:,}***\n"
        f"- Finished Orders: 📦 ***{order['finished']:,}***\n"
        f"- Canceled Orders: ❌ ***{order['canceled']:,}***\n\n"
        "### 👥 Market Overview\n"
        f"- Total Workers: 👷 ***{total_workers:,}***\n"
        f"- Total Customers: 🛍️ ***{total_customers:,}***\n\n"
        "### 🪙 Gold Overview\n"
        f"- Workers Income: 🪙 ***{gold['worker_income']:,}***\n"
        f"- Customers Spent: 🪙 ***{gold['customer_spent']:,}***\n\n"
        "### 🥇 Leaderboard\n"
        "**Top 5 Workers**\n"
        f"{_fmt_users(guild, leaderboard.get('workers', []))}\n\n"
        "**Top 5 Customers**\n"
        f"{_fmt_users(guild, leaderboard.get('customers', []))}\n\n"
        "**Top 5 Items**\n"
        f"{_fmt_items(leaderboard.get('items', []))}"
    )

    embed.set_footer(text="🌟 Starlight Market")
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
            name = member.display_name if member else "Unknown User"

        lines.append(f"{i}. ***{name}*** — 🪙 ***{value:,}***")

    return "\n".join(lines)


def _fmt_items(rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return "- No data"

    lines: List[str] = []

    for i, row in enumerate(rows, start=1):
        name = row.get("name", "Unknown")
        emoji = row.get("item_emoji", "🌟")
        value = int(row.get("value", 0))

        lines.append(f"{i}. ***{emoji} {name}*** — 🏷 ***{value:,}x***")

    return "\n".join(lines)