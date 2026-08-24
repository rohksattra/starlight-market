"""Order flow handlers: entry, claim, close, rating."""
from __future__ import annotations

import asyncio
import logging
from typing import Literal

import discord

from bot.activity_log import log_activity
from bot.handlers.order_presenters import (
    post_transaction_embed,
    publish_news,
    refresh_order_embed,
    require_context,
    sync_order_category,
    target_order_category_id,
)
from bot.handlers.order_staff import OrderStaffMixin
from bot.ui.orders import (
    OrderCategoryView,
    OrderCloseConfirmView,
    OrderConfirmView,
    OrderItemView,
    QuantityModal,
    claim_log_embed,
    customer_total_price,
)
from core.tenant import GameContext
from models.enums import ORDER_MANAGEMENT_ROLES, OrderStatus, ServerRole
from services.items import ItemService
from services.order_claim import OrderClaimService
from services.orders import OrderService
from services.ratings import WorkerRatingService
from utils.cooldown import check_cooldown
from utils.discord_safe import safe_defer, safe_edit_message, safe_respond
from utils.permissions import has_any_role, has_role

log = logging.getLogger("bot.handlers.orders")

# Compat for existing imports.
__all__ = [
    "OrderHandler",
    "get_order_handler",
    "post_transaction_embed",
    "publish_news",
    "refresh_order_embed",
    "require_context",
    "sync_order_category",
    "target_order_category_id",
]


class OrderHandler(OrderStaffMixin):
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
                ctx=ctx,
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
            action=f"Submitted a {rating} star worker rating",
        )

    async def _disable_rating_buttons(self, interaction: discord.Interaction) -> None:
        message = interaction.message
        if message is None or not message.components:
            return
        try:
            view = discord.ui.View.from_message(message)
        except Exception:
            log.exception("Failed to rebuild rating view from message")
            return
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await safe_edit_message(interaction, view=view)

    async def start_order_flow(self, interaction: discord.Interaction) -> None:
        from bot.ui.orders import (
            OrderCategoryView,
            OrderConfirmView,
            OrderItemView,
            QuantityModal,
            customer_total_price,
        )
        from bot.ui.shared import button_notice_content_suffix

        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            return

        ctx = require_context(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="start_order", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        if not has_role(interaction.user, ctx, ServerRole.CUSTOMER):
            await safe_respond(interaction, content="❌ Only **Customers** can create orders.", ephemeral=True)
            return

        category_channel = interaction.guild.get_channel(ctx.channels.new_orders_category)
        if not isinstance(category_channel, discord.CategoryChannel):
            await safe_respond(
                interaction,
                content="❌ Order category channel is not configured properly.",
                ephemeral=True,
            )
            return

        item_serv = ItemService(ctx)
        categories = await item_serv.list_categories()
        if not categories:
            await safe_respond(interaction, content="❌ No item categories available.", ephemeral=True)
            return

        async def on_category(inter: discord.Interaction, category: str) -> None:
            items = await item_serv.list_items_by_category(category)
            if not items:
                await safe_respond(inter, content="❌ No items found in this category.", ephemeral=True)
                return

            async def on_item(inter2: discord.Interaction, item_id: str) -> None:
                if inter2.response.is_done():
                    return

                item = next((i for i in items if i["item_id"] == item_id), None)
                if item is None:
                    await safe_respond(inter2, content="❌ Item not found.", ephemeral=True)
                    return

                if int(item.get("item_price", 0) or 0) <= 0:
                    await safe_respond(
                        inter2,
                        content="❌ This item is not available for order yet.",
                        ephemeral=True,
                    )
                    return

                item_emoji = item.get("item_emoji", "🌟")

                async def on_quantity(inter3: discord.Interaction, qty: int) -> None:
                    await safe_defer(inter3, ephemeral=True)
                    total_price = item["item_price"] * qty

                    async def on_confirm(inter4: discord.Interaction) -> None:
                        await safe_defer(inter4, ephemeral=True)
                        order_serv = OrderService(ctx)

                        try:
                            order = await order_serv.create_order(
                                customer_id=str(inter4.user.id),
                                item_id=item["item_id"],
                                quantity=qty,
                            )
                        except ValueError as exc:
                            await safe_respond(inter4, content=f"❌ {exc}", ephemeral=True)
                            return

                        guild = inter4.guild
                        if guild is None:
                            return

                        try:
                            channel = await self._publish_order_channel(
                                guild=guild,
                                category=category_channel,
                                order=order,
                                ctx=ctx,
                                order_serv=order_serv,
                            )
                        except Exception:
                            log.exception("Failed to create order channel")
                            await order_serv.cancel_order(order=order)
                            await safe_respond(
                                inter4,
                                content=(
                                    "❌ **Failed to create order channel.**\n"
                                    "Order has been canceled automatically.\n"
                                    "You can make it again."
                                ),
                                ephemeral=True,
                            )
                            return

                        total_display = customer_total_price(order)
                        coupon_note = (
                            f"\n🎟 Donor coupon applied — saved 🪙 ***"
                            f"{(order['item_price'] * order['item_quantity']) - total_display:,}***"
                            if order.get("coupon_applied")
                            else ""
                        )
                        await safe_respond(
                            inter4,
                            content=(
                                "✅ **Order Created**\n\n"
                                f"📦 Item: ***{item_emoji} {order['item_name']}***\n"
                                f"🔢 Quantity: 🏷 ***{order['item_quantity']:,}***\n"
                                f"💰 Total: 🪙 ***{total_display:,}***"
                                f"{coupon_note}\n\n"
                                f"📍 Channel: ***{channel.mention}***"
                            ),
                            ephemeral=True,
                        )
                        await log_activity(
                            guild=guild,
                            ctx=ctx,
                            member=inter4.user,
                            action=(
                                f"Created order: {order['item_quantity']:,}x "
                                f"{order['item_name']} in #{channel.name}"
                            ),
                        )

                    await safe_respond(
                        inter3,
                        content=(
                            "📝 **Confirm Order**\n\n"
                            f"📦 Item: ***{item_emoji} {item['item_name']}***\n"
                            f"🔢 Quantity: 🏷 ***{qty:,}***\n"
                            f"💰 Price: 🪙 ***{item['item_price']:,}***\n"
                            f"💰 Total: 🪙 ***{total_price:,}***"
                            f"{button_notice_content_suffix()}"
                        ),
                        view=OrderConfirmView(on_confirm=on_confirm),
                        ephemeral=True,
                    )

                await inter2.response.send_modal(QuantityModal(on_submit=on_quantity, kind="place"))

            await safe_respond(
                inter,
                content="📦 Select item:",
                view=OrderItemView(
                    user_id=inter.user.id,
                    items=items,
                    page=0,
                    page_size=20,
                    on_pick=on_item,
                ),
                ephemeral=True,
            )

        await safe_respond(
            interaction,
            content="📂 Select category:",
            view=OrderCategoryView(
                user_id=interaction.user.id,
                categories=categories,
                page=0,
                page_size=20,
                on_select=on_category,
            ),
            ephemeral=True,
        )


_handler: OrderHandler | None = None


def get_order_handler() -> OrderHandler:
    global _handler
    if _handler is None:
        _handler = OrderHandler()
    return _handler
