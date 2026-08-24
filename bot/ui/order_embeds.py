"""Order embeds, buttons, and modals (UI only)."""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Literal
from uuid import uuid4

import discord
from discord.errors import NotFound

from bot.ui.shared import button_notice_content_suffix, set_starlight_footer
from core.constants import DONOR_COUPON_DISCOUNT_RATE
from core.tenant import GameContext
from utils.assets import item_image_url

log = logging.getLogger("bot.ui.orders")


def fmt(value: int) -> str:
    return f"{value:,}"


def customer_payment_total(
    *,
    item_price: int,
    quantity: int,
    coupon_applied: bool = False,
) -> int:
    total = item_price * quantity
    if coupon_applied:
        total = int(total * (1 - DONOR_COUPON_DISCOUNT_RATE))
    return total


def customer_total_price(order: dict) -> int:
    return customer_payment_total(
        item_price=int(order.get("item_price", 0)),
        quantity=int(order.get("item_quantity", 0)),
        coupon_applied=bool(order.get("coupon_applied")),
    )


def order_description(order: dict, ctx: GameContext | None = None) -> str:
    customer_id = order.get("customer_id")
    item_name = order.get("item_name", "Item")
    item_price = int(order.get("item_price", 0))
    quantity = int(order.get("item_quantity", 0))
    order_claims = order.get("order_claims", {})
    delivered = int(order_claims.get("order_delivered", 0))
    completed = int(order_claims.get("order_completed", 0))
    claimable = int(order_claims.get("order_claimable", 0))
    worker_claims = {
        wid: int(qty)
        for wid, qty in order.get("worker_claims", {}).items()
        if int(qty) > 0
    }
    claimed_total = sum(worker_claims.values())
    total_line = f"- 🪙 ***{fmt(customer_total_price(order))}***"
    if order.get("coupon_applied"):
        total_line += " *(0.5% donor coupon applied)*"
    claimed_lines = (
        "\n".join(f"🏷 ***{fmt(qty)}*** by <@{worker_id}>" for worker_id, qty in worker_claims.items())
        if worker_claims
        else "***🏷 0***"
    )
    bank = f"<@&{ctx.roles.bank_manager}>" if ctx and ctx.roles.bank_manager else "@Bank Manager"
    return (
        f"**Customer**\n"
        f"- ***<@{customer_id}>***\n"
        f"**Item**\n"
        f"- ***{item_name}***\n"
        f"**Quantity**\n"
        f"- 🏷 ***{fmt(quantity)}***\n"
        f"**Price**\n"
        f"- 🪙 ***{fmt(item_price)} each***\n"
        f"**Estimated Total**\n"
        f"{total_line}\n\n"
        f"**__Delivered__**\n"
        f"-# Items delivered to the customer\n"
        f"🏷 ***{fmt(delivered)}***\n\n"
        f"**__Completed__**\n"
        f"-# Items finished by the workers\n"
        f"🏷 ***{fmt(completed)}***\n\n"
        f"**__Claimed__**\n"
        f"-# Items being processed by workers\n"
        f"{claimed_lines}\n"
        f"-# Total claimed\n"
        f"🏷 ***{fmt(claimed_total)}***\n\n"
        f"**__Claimable__**\n"
        f"-# Items available for workers to claim\n"
        f"🏷 ***{fmt(claimable)}***\n\n"
        f"Workers can **Claim** or **Unclaim** using the buttons below.\n\n"
        f"If you need to change the item, quantity, or increase the price, please contact {bank}."
    )


def _item_image_url(ctx: GameContext, item_image: str, item_category: str) -> str:
    return item_image_url(ctx, item_image=item_image, item_category=item_category)


def order_embed(
    *,
    order: dict,
    ctx: GameContext,
    guild: discord.Guild,
) -> tuple[str, discord.Embed]:
    quantity = int(order.get("item_quantity", 0))
    item_name = order.get("item_name", "Item")
    worker_role = guild.get_role(ctx.roles.worker)
    worker_mention = worker_role.mention if worker_role else "@Worker"
    embed = discord.Embed(
        title=f"📦 New Order — ***{fmt(quantity)}x {item_name}***",
        description=order_description(order, ctx),
        color=0xFFD700,
    )
    image_url = _item_image_url(ctx, order.get("item_image", ""), order.get("item_category", ""))
    if image_url:
        embed.set_thumbnail(url=image_url)
    set_starlight_footer(embed, ctx=ctx, detail="Good Luck 💪 & Have Fun 🙃")
    return f"🔊 {worker_mention}", embed


async def update_order_embed(
    *,
    channel: discord.TextChannel,
    order: dict,
    ctx: GameContext,
) -> None:
    embed_message_id = order.get("embed_message_id")
    if not embed_message_id:
        return
    try:
        msg = await channel.fetch_message(int(embed_message_id))
    except discord.NotFound:
        return
    guild = channel.guild
    worker_role = guild.get_role(ctx.roles.worker) if guild else None
    worker_mention = worker_role.mention if worker_role else "@Worker"
    quantity = int(order.get("item_quantity", 0))
    item_name = order.get("item_name", "Item")
    embed = discord.Embed(
        title=f"📦 New Order — ***{fmt(quantity)}x {item_name}***",
        description=order_description(order, ctx),
        color=0xFFD700,
    )
    image_url = _item_image_url(ctx, order.get("item_image", ""), order.get("item_category", ""))
    if image_url:
        embed.set_thumbnail(url=image_url)
    set_starlight_footer(embed, ctx=ctx, detail="Good Luck 💪 & Have Fun 🙃")
    await msg.edit(
        content=f"🔊 {worker_mention}",
        embed=embed,
        allowed_mentions=discord.AllowedMentions.none(),
    )


def order_entry_embed(role_mention: str, ctx: GameContext) -> discord.Embed:
    embed = discord.Embed(
        description=(
            f"Welcome to {ctx.brand.emoji} **{ctx.brand.name}** 🛒\n\n"
            "1️⃣ Click **Order Now**\n"
            "2️⃣ Select category & item\n"
            "3️⃣ Enter quantity\n"
            "4️⃣ Confirm order\n\n"
            f"For custom orders, contact {role_mention}"
        ),
        color=0xFFD700,
    )
    set_starlight_footer(embed, ctx=ctx)
    return embed


def claim_log_embed(
    *,
    worker: discord.Member,
    item_name: str,
    quantity: int,
    channel: discord.TextChannel,
    action: str,
    ctx: GameContext,
    item_emoji: str = "🌟",
    staff: discord.Member | None = None,
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
    set_starlight_footer(embed, ctx=ctx, include_button_notice=False)
    return embed


def order_update_embed(
    *,
    field: Literal["price", "quantity", "customer"],
    old_value: int | str,
    new_value: int | str,
    worker_role: discord.Role | None,
    ctx: GameContext,
) -> tuple[str, discord.Embed]:
    role_mention = worker_role.mention if worker_role else "@Worker"

    if field == "quantity":
        body = (
            f"🏷 **Quantity updated:** ***{int(old_value):,}*** ➡️ ***{int(new_value):,}***"
        )
    elif field == "price":
        body = (
            f"🪙 **Price updated:** ***{int(old_value):,}*** ➡️ ***{int(new_value):,}***"
        )
    elif field == "customer":
        body = f"👤 **Customer updated:** <@{old_value}> ➡️ <@{new_value}>"
    else:
        raise ValueError("Invalid field for order update embed")

    embed = discord.Embed(title="📌 Order Update", description=body, color=0xFFD700)
    set_starlight_footer(embed, ctx=ctx, include_button_notice=False)
    return f"🔔 {role_mention}", embed


def transaction_embed(
    *,
    role: str,
    member: discord.Member,
    order: dict,
    quantity: int,
    ctx: GameContext,
    item_emoji: str = "🌟",
) -> discord.Embed:
    item_name: str = order.get("item_name", "Item")
    emoji: str = item_emoji or "🌟"
    price: int = int(order.get("item_price", 0))
    quantity = int(quantity)
    coupon_applied = bool(order.get("coupon_applied"))

    item_fmt = f"{emoji} {item_name}"
    qty_fmt = f"🏷 ***{fmt(quantity)}x***"
    keep_rate = 1.0 - float(ctx.economy.worker_fee_rate)

    if role == "worker":
        amount = int(price * quantity * keep_rate)
        description = (
            f"***{ctx.brand.name}*** paid 🪙 ***{fmt(amount)}*** to "
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
            f"{qty_fmt} of ***{item_fmt}*** at ***{ctx.brand.name}***."
        )

    embed = discord.Embed(
        title="💰 Transaction Record",
        description=description,
        color=0xFFD700,
    )
    set_starlight_footer(embed, ctx=ctx, include_button_notice=False)
    return embed


def pickup_embed(
    *,
    customer_mention: str,
    bank_manager_role_id: int,
    item_name: str,
    item_price: int,
    quantity: int,
    ctx: GameContext,
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
    set_starlight_footer(embed, ctx=ctx, include_button_notice=False)
    return f"🔔 {customer_mention}", embed


def close_embed(*, bank_manager_role_id: int, ctx: GameContext) -> discord.Embed:
    bank_manager_mention = f"<@&{bank_manager_role_id}>"
    embed = discord.Embed(
        title="✅ Order Ready to be Closed",
        description=(
            "All items have been **successfully delivered**.\n\n"
            f"{bank_manager_mention} may now click **Close Order** "
            "to finalize and remove this order."
        ),
        color=0xFFD700,
    )
    set_starlight_footer(embed, ctx=ctx, include_button_notice=False)
    return embed


def format_rating_stars(average: float, *, max_stars: int = 5) -> str:
    if average <= 0:
        return ""
    full = int(average)
    has_half = (average - full) >= 0.5
    stars: list[str] = []
    for i in range(max_stars):
        if i < full:
            stars.append("★")
        elif i == full and has_half:
            stars.append("☆")
            has_half = False
        else:
            stars.append("✩")
    return "".join(stars)


def worker_rating_embed(
    *,
    worker: discord.Member,
    customer: discord.Member,
    item_name: str,
    item_quantity: int,
    order_channel: discord.TextChannel,
    ctx: GameContext,
    item_emoji: str = "🌟",
) -> tuple[str, discord.Embed]:
    item_fmt = f"{item_emoji} {item_name}"
    qty_fmt = f"🏷 ***{fmt(item_quantity)}x***"
    embed = discord.Embed(
        title="⭐ Rate Worker Performance",
        description=(
            f"***{worker.mention}*** has successfully completed "
            f"{qty_fmt} of ***{item_fmt}*** for your order in "
            f"***{order_channel.mention}***\n\n"
            f"Please take a moment to rate their performance."
        ),
        color=0xFFD700,
    )
    set_starlight_footer(embed, ctx=ctx, include_button_notice=False)
    return f"🔔 {customer.mention}", embed


def worker_rating_summary(*, average: float, count: int) -> str:
    if count <= 0:
        return "No ratings yet"
    stars = format_rating_stars(average)
    return (
        f"{stars} ***{average:.2f}***\n"
        f"***{fmt(count)}*** rating(s)"
    )

