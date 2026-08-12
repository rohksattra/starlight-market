"""Order flow handlers: entry, claim, close, rating, presenter helpers."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

import discord

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
log = logging.getLogger("bot.handlers.orders")


async def sync_order_category(*, channel: discord.TextChannel, order: dict, ctx: GameContext) -> None:
    guild = channel.guild
    if guild is None:
        return
    if order["order_status"] not in {OrderStatus.NEW, OrderStatus.CLAIMED}:
        return
    claims = order["order_claims"]
    total = order["item_quantity"]
    target_category_id = (
        ctx.channels.new_orders_category
        if claims["order_claimable"] == total
        else ctx.channels.claimed_orders_category
    )
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

    transaction_channel_id = (
        ctx.channels.worker_transaction
        if target == "worker"
        else ctx.channels.customer_transaction
    )
    tx_channel = guild.get_channel(transaction_channel_id)

    if isinstance(tx_channel, discord.TextChannel) and member:
        msg = await tx_channel.send(
            embed=transaction_embed(
                role=target,
                member=member,
                order=order,
                quantity=quantity,
                ctx=ctx,
                item_emoji=item_emoji,
            )
        )
        await publish_news(msg)

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
            )
            await order_channel.send(content=content, embed=embed)

    if target == "customer" and result.get("delivered"):
        await order_channel.send(
            embed=close_embed(bank_manager_role_id=ctx.roles.bank_manager),
            view=OrderCloseView(),
            allowed_mentions=discord.AllowedMentions(roles=True),
        )


def require_context(interaction: discord.Interaction) -> GameContext | None:
    if interaction.guild is None:
        return None
    return get_context(interaction.guild.id)


class OrderHandler:
    async def handle_claim_refresh(self, interaction: discord.Interaction) -> None:
        ctx = require_context(interaction)
        if ctx is None or not isinstance(interaction.channel, discord.TextChannel):
            return
        order = await OrderService(ctx).get_by_channel_id(str(interaction.channel.id))
        if not order:
            return
        await refresh_order_embed(channel=interaction.channel, order=order, ctx=ctx)

    async def handle_claim_action(
        self,
        interaction: discord.Interaction,
        *,
        action: Literal["claim", "unclaim"],
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(
                interaction,
                content="❌ This action must be used in an order channel.",
                ephemeral=True,
            )
            return

        ctx = require_context(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_role(interaction.user, ctx, ServerRole.WORKER):
            await safe_respond(interaction, content="❌ Only **Workers** can use this action.", ephemeral=True)
            return

        order_serv = OrderService(ctx)
        claim_serv = OrderClaimService(ctx)
        item_serv = ItemService(ctx)

        order = await order_serv.get_by_channel_id(str(interaction.channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return

        worker_id = str(interaction.user.id)
        if order["customer_id"] == worker_id:
            await safe_respond(interaction, content="❌ You cannot claim your own order.", ephemeral=True)
            return

        if action == "claim":
            try:
                updated = await claim_serv.claim(order_id=order["order_id"], worker_id=worker_id, qty=quantity)
            except ValueError as exc:
                await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
                return
        else:
            try:
                updated = await claim_serv.unclaim(order_id=order["order_id"], worker_id=worker_id, qty=quantity)
            except ValueError as exc:
                await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
                return

        await sync_order_category(channel=interaction.channel, order=updated, ctx=ctx)
        await refresh_order_embed(channel=interaction.channel, order=updated, ctx=ctx)

        log_channel = interaction.guild.get_channel(ctx.channels.claim_log) if interaction.guild else None
        if isinstance(log_channel, discord.TextChannel):
            emoji = await item_serv.get_item_emoji(order["item_id"])
            embed = claim_log_embed(
                worker=interaction.user,
                item_name=updated["item_name"],
                item_emoji=emoji,
                quantity=quantity,
                channel=interaction.channel,
                action=action,
            )
            await log_channel.send(embed=embed)

        verb = "Claimed" if action == "claim" else "Unclaimed"
        await safe_respond(interaction, content=f"✅ {verb} ***{quantity:,}*** item(s).", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"Claimed {quantity:,}x {updated['item_name']} "
                f"in #{interaction.channel.name}"
                if action == "claim"
                else f"Unclaimed {quantity:,}x {updated['item_name']} "
                f"in #{interaction.channel.name}"
            ),
        )

    async def handle_close_order_button(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid user.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="close_order", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = require_context(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Must be used in an order channel.", ephemeral=True)
            return

        order = await OrderService(ctx).get_by_channel_id(str(interaction.channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return

        if order["order_status"] != OrderStatus.DELIVERED:
            await safe_respond(interaction, content="❌ Only delivered orders can be closed.", ephemeral=True)
            return

        view = OrderCloseConfirmView()
        await interaction.response.send_message(
            "⚠️ **Confirmation Required**\n\nAre you sure you want to **FINALIZE** this order?",
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()

    async def finalize_close_order(
        self,
        interaction: discord.Interaction,
        *,
        channel: discord.TextChannel,
    ) -> None:
        ctx = require_context(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        order_serv = OrderService(ctx)
        order = await order_serv.get_by_channel_id(str(channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return

        if order["order_status"] != OrderStatus.DELIVERED:
            await safe_respond(interaction, content="❌ Only delivered orders can be closed.", ephemeral=True)
            return

        try:
            await order_serv.close_order(order=order)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"Closed order #{order.get('order_number')} "
                f"({order.get('item_name')}) in #{channel.name}"
            ),
        )
        await channel.send("✅ Order closed. Channel will be deleted.")
        await asyncio.sleep(5)
        await channel.delete(reason="Order closed")

    async def handle_rating(self, interaction: discord.Interaction, *, rating: int) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid user.", ephemeral=True)
            return
        if interaction.message is None:
            await safe_respond(interaction, content="❌ Message not found.", ephemeral=True)
            return

        ctx = require_context(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        transaction_id = str(interaction.message.id)
        try:
            await WorkerRatingService(ctx).submit_rating(
                transaction_id=transaction_id,
                customer_id=str(interaction.user.id),
                rating=rating,
            )
        except PermissionError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            await self._disable_rating_buttons(interaction)
            return
        except RuntimeError:
            await safe_respond(interaction, content="❌ Failed to submit rating.", ephemeral=True)
            return

        await self._disable_rating_buttons(interaction)
        await safe_respond(
            interaction,
            content=f"✅ Thank you! You rated the worker **{rating}⭐**.",
            ephemeral=True,
        )
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=f"Rated worker {rating} star{'s' if rating != 1 else ''}",
        )

    async def _disable_rating_buttons(self, interaction: discord.Interaction) -> None:
        message = interaction.message
        if message is None or not message.components:
            return
        try:
            view = discord.ui.View.from_message(message)
        except Exception:
            return
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await safe_edit_message(interaction, view=view)


_handler: OrderHandler | None = None


def get_order_handler() -> OrderHandler:
    global _handler
    if _handler is None:
        _handler = OrderHandler()
    return _handler
