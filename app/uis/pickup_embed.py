# app/uis/pickup_embed.py
from __future__ import annotations

import discord


def pickup_embed(
    *, customer_mention: str, bank_manager_role_id: int, item_name: str, quantity: int, total_price: int, item_emoji: str = "🌟"
) -> tuple[str, discord.Embed]:
    bank_manager_mention = f"<@&{bank_manager_role_id}>"
    embed = discord.Embed(
        title="📦 Order Ready for Pickup",
        description=(
            f"Your 🏷 ***{quantity:,}x {item_emoji} {item_name}*** is ready.\n"  # Tambahkan emoji sebelum item_name
            f"Total Price 🪙 ***{total_price:,}***\n\n"
            f"Please ping {bank_manager_mention} to pickup your order."
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")
    return f"🔔 {customer_mention}", embed