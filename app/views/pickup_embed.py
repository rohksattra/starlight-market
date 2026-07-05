from __future__ import annotations

import discord

from app.views.order_embed import customer_payment_total


def fmt(value: int) -> str:
    return f"{value:,}"


def pickup_embed(
    *,
    customer_mention: str,
    bank_manager_role_id: int,
    item_name: str,
    item_price: int,
    quantity: int,
    item_emoji: str = "🌟",
    coupon_applied: bool = False,
) -> tuple[str, discord.Embed]:
    bank_manager_mention = f"<@&{bank_manager_role_id}>"

    amount = customer_payment_total(
        item_price=item_price,
        quantity=quantity,
        coupon_applied=coupon_applied,
    )

    item_fmt = f"{item_emoji} {item_name}"
    qty_fmt = f"🏷 ***{fmt(quantity)}x***"
    total_fmt = f"🪙 ***{fmt(amount)}***"
    if coupon_applied:
        total_fmt += " *(0.5% donor coupon applied)*"

    embed = discord.Embed(
        title="📦 Order Ready for Pickup",
        description=(
            f"Your {qty_fmt} of ***{item_fmt}*** is ready.\n"
            f"Total Price {total_fmt}\n\n"
            f"Please ping {bank_manager_mention} to pickup your order.\n\n"
            f"You have ⏳ ***7 days*** to pickup or to inform Bank Manager when will you pickup the order. "
            f"If no information after the time, the Market will sell the items."
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")

    return f"🔔 {customer_mention}", embed
