# app/uis/order_update_embed.py
from __future__ import annotations

from typing import Literal

import discord


def _fmt(value: int) -> str:
    return f"{value:,}"


OrderUpdateField = Literal["price", "quantity"]


def order_update_embed(*, field: OrderUpdateField, old_value: int, new_value: int, worker_role: discord.Role | None) -> discord.Embed:
    if field == "quantity":
        label = "Quantity"
        icon = "🏷"
    elif field == "price":
        label = "Price"
        icon = "🪙"
    else:
        raise ValueError("Invalid field for order update embed")
    role_mention = worker_role.mention if worker_role else "@Worker"
    embed = discord.Embed(
        title="📌 Order Update",
        description=(
            f"{role_mention}\n"
            f"{icon} **{label} updated:** "
            f"***{_fmt(old_value)}*** ➡️ ***{_fmt(new_value)}***"
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")
    return embed
