from __future__ import annotations

from typing import Literal

import discord


def _fmt(value: int) -> str:
    return f"{value:,}"


OrderUpdateField = Literal["price", "quantity", "customer"]


def order_update_embed(
    *,
    field: OrderUpdateField,
    old_value: int | str,
    new_value: int | str,
    worker_role: discord.Role | None,
) -> tuple[str, discord.Embed]:
    role_mention = worker_role.mention if worker_role else "@Worker"

    if field == "quantity":
        label, icon = "Quantity", "🏷"
        body = f"{icon} **{label} updated:** ***{_fmt(int(old_value))}*** ➡️ ***{_fmt(int(new_value))}***"
    elif field == "price":
        label, icon = "Price", "🪙"
        body = f"{icon} **{label} updated:** ***{_fmt(int(old_value))}*** ➡️ ***{_fmt(int(new_value))}***"
    elif field == "customer":
        body = f"👤 **Customer updated:** <@{old_value}> ➡️ <@{new_value}>"
    else:
        raise ValueError("Invalid field for order update embed")

    embed = discord.Embed(title="📌 Order Update", description=body, color=0xFFD700)
    embed.set_footer(text="🌟 Starlight Market")
    return f"🔔 {role_mention}", embed
