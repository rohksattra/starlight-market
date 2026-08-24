"""Order flow handlers: entry, claim, close, rating, presenter helpers."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

import discord
from discord.ext import commands

from bot.activity_log import log_activity
from bot.ui.orders import (
    OrderCloseConfirmView,
    OrderCloseView,
    RatingWorkerButton,
    claim_log_embed,
    close_embed,
    pickup_embed,
    transaction_embed,
    update_order_embed,
    worker_rating_embed,
)
from core.tenant import GameContext, get_context
from models.enums import ORDER_MANAGEMENT_ROLES, OrderStatus, ServerRole
from services.items import ItemService
from services.order_claim import OrderClaimService
from services.orders import OrderService
from services.ratings import WorkerRatingService
from utils.cooldown import check_cooldown
from utils.discord_safe import safe_defer, safe_edit_message, safe_respond
from utils.permissions import has_any_role, has_role

IncomeTarget = Literal["worker", "customer"]
log = logging.getLogger("bot.handlers.order_presenters")


def target_order_category_id(order: dict[str, Any], ctx: GameContext) -> int | None:
    """New vs Claimed category. Completed is moved after worker income finishes."""
    if order["order_status"] not in {OrderStatus.NEW, OrderStatus.CLAIMED}:
        return None
    claims = order["order_claims"]
    if int(claims["order_claimable"]) == int(order["item_quantity"]):
        return ctx.channels.new_orders_category
    return ctx.channels.claimed_orders_category


async def sync_order_category(*, channel: discord.TextChannel, order: dict, ctx: GameContext) -> None:
    guild = channel.guild
    if guild is None:
        return
    target_category_id = target_order_category_id(order, ctx)
    if target_category_id is None:
        return
    category = guild.get_channel(target_category_id)
    if isinstance(category, discord.CategoryChannel):
        await channel.edit(category=category, sync_permissions=True)


async def refresh_order_embed(*, channel: discord.TextChannel, order: dict, ctx: GameContext) -> None:
    await update_order_embed(channel=channel, order=order, ctx=ctx)


async def publish_news(message: discord.Message) -> None:
    channel = message.channel
    if not isinstance(channel, discord.TextChannel) or not channel.is_news():
        return
    try:
        await message.publish()
    except discord.HTTPException:
        pass


async def post_transaction_embed(
    *,
    guild: discord.Guild,
    ctx: GameContext,
    target: IncomeTarget,
    member: discord.Member | None,
    item_name: str,
    item_price: int,
    quantity: int,
    item_emoji: str = "🌟",
    coupon_applied: bool = False,
) -> None:
    if member is None:
        return
    channel_id = (
        ctx.channels.worker_transaction
        if target == "worker"
        else ctx.channels.customer_transaction
    )
    tx_channel = guild.get_channel(channel_id)
    if not isinstance(tx_channel, discord.TextChannel):
        return
    msg = await tx_channel.send(
        embed=transaction_embed(
            role=target,
            member=member,
            order={
                "item_name": item_name,
                "item_price": item_price,
                "coupon_applied": coupon_applied,
            },
            quantity=quantity,
            ctx=ctx,
            item_emoji=item_emoji,
        )
    )
    await publish_news(msg)


async def after_income_recorded(
    *,
    guild: discord.Guild,
    order_channel: discord.TextChannel,
    order: dict,
    target: IncomeTarget,
    user_id: str,
    quantity: int,
    result: dict[str, Any],
    ctx: GameContext,
    worker_ratings_serv: WorkerRatingService | None = None,
) -> None:
    ratings_serv = worker_ratings_serv or WorkerRatingService(ctx)
    item_serv = ItemService(ctx)

    member = guild.get_member(int(user_id))
    item_emoji = await item_serv.get_item_emoji(order["item_id"])

    await refresh_order_embed(channel=order_channel, order=order, ctx=ctx)
    await post_transaction_embed(
        guild=guild,
        ctx=ctx,
        target=target,
        member=member,
        item_name=str(order.get("item_name", "Item")),
        item_price=int(order.get("item_price", 0)),
        quantity=quantity,
        item_emoji=item_emoji,
        coupon_applied=bool(order.get("coupon_applied")),
    )

    if target == "worker" and member:
        rating_channel = guild.get_channel(ctx.channels.rating_message)
        if isinstance(rating_channel, discord.TextChannel):
            customer = guild.get_member(int(order["customer_id"]))
            if customer:
                content, embed = worker_rating_embed(
                    worker=member,
                    customer=customer,
                    item_name=order["item_name"],
                    item_emoji=item_emoji,
                    item_quantity=quantity,
                    order_channel=order_channel,
                    ctx=ctx,
                )
                msg = await rating_channel.send(
                    content=content,
                    embed=embed,
                    view=RatingWorkerButton(),
                )
                await ratings_serv.request_rating(
                    transaction_id=str(msg.id),
                    worker_id=user_id,
                    customer_id=str(customer.id),
                )

    if target == "worker" and result.get("finished"):
        category = guild.get_channel(ctx.channels.completed_orders_category)
        if isinstance(category, discord.CategoryChannel):
            await order_channel.edit(category=category, sync_permissions=True)

        customer = guild.get_member(int(order["customer_id"]))
        if customer:
            completed_qty = int(order["order_claims"]["order_completed"])
            content, embed = pickup_embed(
                customer_mention=customer.mention,
                bank_manager_role_id=ctx.roles.bank_manager,
                item_name=order["item_name"],
                item_emoji=item_emoji,
                item_price=int(order["item_price"]),
                quantity=completed_qty,
                coupon_applied=bool(order.get("coupon_applied")),
                ctx=ctx,
            )
            await order_channel.send(content=content, embed=embed)

    if target == "customer" and result.get("delivered"):
        await order_channel.send(
            embed=close_embed(bank_manager_role_id=ctx.roles.bank_manager, ctx=ctx),
            view=OrderCloseView(),
            allowed_mentions=discord.AllowedMentions(roles=True),
        )


def require_context(interaction: discord.Interaction) -> GameContext | None:
    if interaction.guild is None:
        return None
    return get_context(interaction.guild.id)

