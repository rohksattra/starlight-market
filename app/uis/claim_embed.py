# app/uis/claim_embed.py
from __future__ import annotations

import discord
from typing import Literal


ClaimAction = Literal["claim", "unclaim", "force_claim", "force_unclaim"]


def claim_log_embed(
    *, worker: discord.Member, item_name: str, quantity: int, channel: discord.TextChannel,
    action: ClaimAction, staff: discord.Member | None = None, item_emoji: str = "🌟",
) -> discord.Embed:

    emoji = item_emoji or "🌟"
    qty = f"***{quantity:,}x***"
    item = f"***{emoji} {item_name}***"
    place = f"***{channel.mention}***"
    worker_m = f"***{worker.mention}***"
    staff_m = f"***{staff.mention}***" if staff else "***Staff***"

    if action == "claim":
        text = f"{worker_m} has claimed 🏷 {qty} of {item} in {place}"
    elif action == "unclaim":
        text = f"{worker_m} has unclaimed 🏷 {qty} of {item} in {place}"
    elif action == "force_claim":
        text = f"{staff_m} forced {worker_m} to claim 🏷 {qty} of {item} in {place}"
    elif action == "force_unclaim":
        text = f"{staff_m} forced {worker_m} to unclaim 🏷 {qty} of {item} in {place}"
    else:
        text = "Unknown claim action."

    embed = discord.Embed(
        title="📌 Order Claim Update",
        description=text,
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")

    return embed