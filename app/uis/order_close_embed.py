# app/uis/order_close_embed.py
from __future__ import annotations

import discord


def close_embed(*, bank_manager_role_id: int) -> discord.Embed:
    bank_manager_mention = f"<@&{bank_manager_role_id}>"
    embed = discord.Embed(
        title="✅ Order Ready to be Closed",
        description=(
            "All items have been **successfully delivered**.\n\n"
            f"{bank_manager_mention} may now use the ***!close*** command "
            "to finalize and remove this order."
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")
    return embed
