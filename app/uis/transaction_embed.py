# app/uis/transaction.py
from __future__ import annotations

from typing import Literal, Dict, Any

import discord

from core.config import WORKER_FEE_RATE


TransactionRole = Literal["worker", "customer"]


def fmt(value: int) -> str:
    return f"{value:,}"


def transaction_embed(*, role: TransactionRole, member: discord.Member, order: Dict[str, Any], quantity: int) -> discord.Embed:
    item_name: str = order.get("item_name", "Item")
    emoji: str = order.get("item_emoji", "🌟") or "🌟"
    price: int = int(order.get("item_price", 0))
    quantity = int(quantity)

    item_fmt = f"{emoji} {item_name}"
    qty_fmt = f"🏷 ***{fmt(quantity)}x***"

    if role == "worker":
        amount = int(price * quantity * WORKER_FEE_RATE)
        description = (
            f"***Starlight Market*** paid 🪙 ***{fmt(amount)}*** to "
            f"{member.mention} for {qty_fmt} of ***{item_fmt}***."
        )
    else:
        amount = price * quantity
        description = (
            f"{member.mention} spent 🪙 ***{fmt(amount)}*** for "
            f"{qty_fmt} of ***{item_fmt}*** at ***Starlight Market***."
        )

    embed = discord.Embed(
        title="💰 Transaction Record",
        description=description,
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")

    return embed
