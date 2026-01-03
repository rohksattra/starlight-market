# app/uis/claim_embed.py
from __future__ import annotations

import discord
from typing import Literal


ClaimAction = Literal["claim", "unclaim", "force_claim", "force_unclaim"]


def claim_log_embed(
    *, worker: discord.Member, item_name: str, quantity: int, channel: discord.TextChannel, action: ClaimAction, staff: discord.Member | None = None,
) -> discord.Embed:
    if action == "claim":
        description = (
            f"***{worker.mention}*** has claimed "
            f"🏷 ***{quantity:,}x*** of ***{item_name}*** "
            f"in ***{channel.mention}***"
        )
    elif action == "unclaim":
        description = (
            f"***{worker.mention}*** has unclaimed "
            f"🏷 ***{quantity:,}x*** of ***{item_name}*** "
            f"in ***{channel.mention}***"
        )
    elif action == "force_claim":
        staff_mention = staff.mention if staff else "**Staff**"
        description = (
            f"***{staff_mention}*** forced ***{worker.mention}*** to claim "
            f"🏷 ***{quantity:,}x*** of ***{item_name}*** "
            f"in ***{channel.mention}***"
        )
    elif action == "force_unclaim":
        staff_mention = staff.mention if staff else "**Staff**"
        description = (
            f"***{staff_mention}*** forced ***{worker.mention}*** to unclaim "
            f"🏷 ***{quantity:,}x*** of ***{item_name}*** "
            f"in ***{channel.mention}***"
        )
    else:
        description = "Unknown claim action."
    embed = discord.Embed(
        title="📌 Order Claim Update",
        description=description,
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")

    return embed
