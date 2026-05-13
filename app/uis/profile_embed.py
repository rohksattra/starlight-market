from __future__ import annotations

from typing import List

import discord

from core.config import settings
from app.services.tier_role_service import (
    customer_tier_role_for_spent,
    worker_tier_role_for_income,
)
from app.uis.worker_rating_embed import worker_rating_summary


def _display_worker_role_id(total_income: int) -> int:
    if total_income <= 0:
        return settings.WORKER_ROLE_ID
    tier_id = worker_tier_role_for_income(total_income)
    return tier_id if tier_id is not None else settings.WORKER_ROLE_ID


def _display_customer_role_id(total_spent: int) -> int:
    if total_spent <= 0:
        return settings.CUSTOMER_ROLE_ID
    tier_id = customer_tier_role_for_spent(total_spent)
    return tier_id if tier_id is not None else settings.CUSTOMER_ROLE_ID


def _role_mention(guild: discord.Guild | None, role_id: int) -> str:
    if guild is not None:
        role = guild.get_role(role_id)
        if role is not None:
            return role.mention
    return f"<@&{role_id}>"


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
    color = 0xFFD700
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
    income_i = int(total_income)
    spent_i = int(total_spent)
    worker_role_line = _role_mention(member.guild, _display_worker_role_id(income_i))
    customer_role_line = _role_mention(member.guild, _display_customer_role_id(spent_i))
    embed = discord.Embed(
        title=f"🪧 {member.display_name}'s Profile",
        color=color,
    )
    embed.description = (
        f"### 💪 As {worker_role_line}\n"
        f"Active Claimed Orders: ***{len(worker_orders)}***\n"
        f"{chr(10).join(worker_orders) if worker_orders else '- No active claimed orders'}\n\n"
        f"Top Worker: 🥇 ***{worker_rank_text}***\n"
        f"Gold Income: 🪙 ***{income_i:,}***\n\n"
        "**⭐ Worker Rating**\n"
        f"{rating_text}\n\n"
        f"### 🛒 As {customer_role_line}\n"
        f"Active Orders Placed: ***{len(customer_orders)}***\n"
        f"{chr(10).join(customer_orders) if customer_orders else '- No active orders'}\n\n"
        f"Top Customer: 🥇 ***{customer_rank_text}***\n"
        f"Gold Spent: 🪙 ***{spent_i:,}***"
    )
    embed.set_footer(text="🌟 Starlight Market")
    return embed
