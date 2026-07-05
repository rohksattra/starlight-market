from __future__ import annotations

import discord

from app.views.embed_footer import set_starlight_footer


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
    set_starlight_footer(embed)
    return embed
