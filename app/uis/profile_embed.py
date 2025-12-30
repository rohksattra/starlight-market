# app/uis/profile_embed.py
from __future__ import annotations

from typing import List

import discord

from app.uis.worker_rating_embed import worker_rating_summary


def profile_embed(
    *,
    member: discord.Member,
    worker_orders: List[str],
    customer_orders: List[str],
    worker_rank: int | None,
    customer_rank: int | None,
    total_income: int,
    total_spent: int,
    worker_rating_avg: float = 0.0,
    worker_rating_count: int = 0,
) -> discord.Embed:
    color = (member.color if member.color.value != 0 else discord.Color.gold())
    rating_text = worker_rating_summary(average=worker_rating_avg, count=worker_rating_count)
    worker_rank_text = (
        f"#{worker_rank:,}"
        if worker_rank is not None
        else "Not ranked yet"
    )
    customer_rank_text = (
        f"#{customer_rank:,}"
        if customer_rank is not None
        else "Not ranked yet"
    )
    embed = discord.Embed(
        title=f"🪧 {member.display_name}'s Profile",
        color=color,
    )
    embed.description = (
        "### 💪 As a Worker\n"
        f"Active Claimed Orders: ***{len(worker_orders)}***\n"
        f"{chr(10).join(worker_orders) if worker_orders else '- No active claimed orders'}\n\n"
        f"Top Worker: 🥇 ***{worker_rank_text}***\n"
        f"Gold Income: 🪙 ***{total_income:,}***\n\n"
        "**⭐ Worker Rating**\n"
        f"{rating_text}\n\n"
        "### 🛒 As a Customer\n"
        f"Active Orders Placed: ***{len(customer_orders)}***\n"
        f"{chr(10).join(customer_orders) if customer_orders else '- No active orders'}\n\n"
        f"Top Customer: 🥇 ***{customer_rank_text}***\n"
        f"Gold Spent: 🪙 ***{total_spent:,}***"
    )
    embed.set_footer(text="🌟 Starlight Market")
    return embed
