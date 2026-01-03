# app/uis/order_entry_embed.py
from __future__ import annotations

import discord


def order_entry_embed(role_mention: str) -> discord.Embed:
    embed = discord.Embed(
        description=(
            "Welcome to 🌟 **Starlight Market** 🛒\n\n"
            "1️⃣ Click **Order Now**\n"
            "2️⃣ Select category & item\n"
            "3️⃣ Enter quantity\n"
            "4️⃣ Confirm order\n\n"
            f"For custom orders, contact {role_mention}"
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")
    return embed
