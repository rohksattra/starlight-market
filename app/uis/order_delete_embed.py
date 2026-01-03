# app/uis/order_delete_embed.py
from __future__ import annotations

import discord


def channel_delete_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🗑️ Channel Deletion",
        description=(
            "This order has been successfully verified.\n\n"
            "**This channel will be deleted in 5 seconds.**"
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")
    return embed
