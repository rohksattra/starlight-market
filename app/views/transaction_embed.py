from __future__ import annotations

from typing import Literal, Dict, Any

import discord

from core.config import WORKER_FEE_RATE
from app.views.order_embed import customer_payment_total


TransactionRole = Literal["worker", "customer"]


def fmt(value: int) -> str:
    return f"{value:,}"


def transaction_embed(
    *,
    role: TransactionRole,
    member: discord.Member,
    order: Dict[str, Any],
    quantity: int,
    item_emoji: str = "🌟",
) -> discord.Embed:
    item_name: str = order.get("item_name", "Item")
    emoji: str = item_emoji or "🌟"
    price: int = int(order.get("item_price", 0))
    quantity = int(quantity)
    coupon_applied = bool(order.get("coupon_applied"))

    item_fmt = f"{emoji} {item_name}"
    qty_fmt = f"🏷 ***{fmt(quantity)}x***"

    if role == "worker":
        amount = int(price * quantity * WORKER_FEE_RATE)
        description = (
            f"***Starlight Market*** paid 🪙 ***{fmt(amount)}*** to "
            f"{member.mention} for {qty_fmt} of ***{item_fmt}***."
        )
    else:
        amount = customer_payment_total(
            item_price=price,
            quantity=quantity,
            coupon_applied=coupon_applied,
        )
        coupon_note = " *(0.5% donor coupon applied)*" if coupon_applied else ""
        description = (
            f"{member.mention} spent 🪙 ***{fmt(amount)}***{coupon_note} for "
            f"{qty_fmt} of ***{item_fmt}*** at ***Starlight Market***."
        )

    embed = discord.Embed(
        title="💰 Transaction Record",
        description=description,
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")

    return embed
