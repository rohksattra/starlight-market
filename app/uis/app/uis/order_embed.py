# app/uis/order_embed.py
from __future__ import annotations

from typing import Dict, Any, Tuple

import discord
from discord import TextChannel


def fmt(value: int) -> str:
    return f"{value:,}"


def order_description(order: Dict[str, Any]) -> str:
    customer_id = order.get("customer_id")
    item_name = order.get("item_name", "Item")
    item_price = int(order.get("item_price", 0))
    quantity = int(order.get("item_quantity", 0))
    order_claims = order.get("order_claims", {})
    delivered = int(order_claims.get("order_delivered", 0))
    completed = int(order_claims.get("order_completed", 0))
    claimable = int(order_claims.get("order_claimable", 0))
    worker_claims: Dict[str, int] = {wid: int(qty) for wid, qty in order.get("worker_claims", {}).items() if int(qty) > 0}
    claimed_total = sum(worker_claims.values())
    claimed_lines = (
        "\n".join(
            f"🏷 ***{fmt(qty)}*** by <@{worker_id}>"
            for worker_id, qty in worker_claims.items()
        )
        if worker_claims
        else "***🏷 0***"
    )
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
        f"- 🪙 ***{fmt(item_price * quantity)}***\n\n"
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
        f"Workers can accept the order using **/claim**\n"
        f"or cancel with **/unclaim**"
    )


def order_embed(*, order: Dict[str, Any], worker_role_id: int, guild: discord.Guild) -> Tuple[str, discord.Embed]:
    quantity = int(order.get("item_quantity", 0))
    item_name = order.get("item_name", "Item")
    worker_role = guild.get_role(worker_role_id)
    worker_mention = worker_role.mention if worker_role else "@Worker"
    embed = discord.Embed(
        title=f"📦 New Order — ***{fmt(quantity)}x {item_name}***",
        description=order_description(order),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market\nGood Luck 💪 & Have Fun 🙃")
    return f"🔊 {worker_mention}", embed


async def update_order_embed(*, channel: TextChannel, order: Dict[str, Any], worker_role_id: int) -> None:
    embed_message_id = order.get("embed_message_id")
    if not embed_message_id:
        return
    try:
        msg = await channel.fetch_message(int(embed_message_id))
    except discord.NotFound:
        return
    guild = channel.guild
    worker_role = guild.get_role(worker_role_id) if guild else None
    worker_mention = worker_role.mention if worker_role else "@Worker"
    quantity = int(order.get("item_quantity", 0))
    item_name = order.get("item_name", "Item")
    embed = discord.Embed(
        title=f"📦 New Order — ***{fmt(quantity)}x {item_name}***",
        description=order_description(order),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market\nGood Luck 💪 & Have Fun 🙃")
    await msg.edit(
        content=f"🔊 {worker_mention}",
        embed=embed,
    )
