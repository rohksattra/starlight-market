# app/uis/pickup_embed.py
from __future__ import annotations

import discord


def fmt(value: int) -> str:
    return f"{value:,}"


def pickup_embed(
    *, customer_mention: str, bank_manager_role_id: int, item_name: str, quantity: int, total_price: int, item_emoji: str = "🌟"
) -> tuple[str, discord.Embed]:
    bank_manager_mention = f"<@&{bank_manager_role_id}>"

    item_fmt = f"{item_emoji} {item_name}"
    qty_fmt = f"🏷 ***{fmt(quantity)}x***"
    total_fmt = f"🪙 ***{fmt(total_price)}***"

    embed = discord.Embed(
        title="📦 Order Ready for Pickup",
        description=(
            f"Your {qty_fmt} of ***{item_fmt}*** is ready.\n"
            f"Total Price {total_fmt}\n\n"
            f"Please ping {bank_manager_mention} to pickup your order.\n\n"
            f"You have ⏳ ***7 days*** to pickup or to inform Bank Manager when will you pickup the order. If no information during after the time, the Market will sell the items."
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")

    return f"🔔 {customer_mention}", embed