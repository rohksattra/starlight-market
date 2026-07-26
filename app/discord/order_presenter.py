from __future__ import annotations

from typing import Any, Literal

import discord

from core.config import settings
from app.domains.enums.order_status_enum import OrderStatus
from app.services.item_service import ItemService
from app.services.worker_rating_service import WorkerRatingService
from app.views.order_close_embed import close_embed
from app.views.order_embed import update_order_embed
from app.views.pickup_embed import pickup_embed
from app.views.transaction_embed import transaction_embed
from app.views.worker_rating_button import RatingWorkerButton
from app.views.worker_rating_embed import worker_rating_embed
from utils.discord_publish import publish_news


IncomeTarget = Literal["worker", "customer"]


async def sync_order_category(*, channel: discord.TextChannel, order: dict) -> None:
    guild = channel.guild
    if guild is None:
        return
    if order["order_status"] not in {OrderStatus.NEW, OrderStatus.CLAIMED}:
        return
    claims = order["order_claims"]
    total = order["item_quantity"]
    target_category_id = (
        settings.NEW_ORDERS_CATEGORY_ID
        if claims["order_claimable"] == total
        else settings.CLAIMED_ORDERS_CATEGORY_ID
    )
    category = guild.get_channel(target_category_id)
    if isinstance(category, discord.CategoryChannel):
        await channel.edit(category=category, sync_permissions=True)


async def refresh_order_embed(*, channel: discord.TextChannel, order: dict) -> None:
    await update_order_embed(
        channel=channel,
        order=order,
        worker_role_id=settings.WORKER_ROLE_ID,
    )


async def after_income_recorded(
    *,
    guild: discord.Guild,
    order_channel: discord.TextChannel,
    order: dict,
    target: IncomeTarget,
    user_id: str,
    quantity: int,
    result: dict[str, Any],
    worker_ratings_serv: WorkerRatingService | None = None,
) -> None:
    ratings_serv = worker_ratings_serv or WorkerRatingService()
    item_serv = ItemService()

    member = guild.get_member(int(user_id))
    item_emoji = await item_serv.get_item_emoji(order["item_id"])

    await refresh_order_embed(channel=order_channel, order=order)

    transaction_channel_id = (
        settings.WORKER_TRANSACTION_CHANNEL_ID
        if target == "worker"
        else settings.CUSTOMER_TRANSACTION_CHANNEL_ID
    )
    tx_channel = guild.get_channel(transaction_channel_id)

    if isinstance(tx_channel, discord.TextChannel) and member:
        msg = await tx_channel.send(
            embed=transaction_embed(
                role=target,
                member=member,
                order=order,
                quantity=quantity,
                item_emoji=item_emoji,
            )
        )
        await publish_news(msg)

    if target == "worker" and member:
        rating_channel = guild.get_channel(settings.RATING_MESSAGE_CHANNEL_ID)
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
        category = guild.get_channel(settings.COMPLETED_ORDERS_CATEGORY_ID)
        if isinstance(category, discord.CategoryChannel):
            await order_channel.edit(category=category, sync_permissions=True)

        customer = guild.get_member(int(order["customer_id"]))
        if customer:
            completed_qty = int(order["order_claims"]["order_completed"])
            content, embed = pickup_embed(
                customer_mention=customer.mention,
                bank_manager_role_id=settings.BANK_MANAGER_ROLE_ID,
                item_name=order["item_name"],
                item_emoji=item_emoji,
                item_price=int(order["item_price"]),
                quantity=completed_qty,
                coupon_applied=bool(order.get("coupon_applied")),
            )
            await order_channel.send(content=content, embed=embed)

    if target == "customer" and result.get("delivered"):
        from app.views.order_close_view import OrderCloseView

        await order_channel.send(
            embed=close_embed(bank_manager_role_id=settings.BANK_MANAGER_ROLE_ID),
            view=OrderCloseView(),
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
