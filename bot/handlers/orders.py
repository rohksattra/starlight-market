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

    async def handle_record_income(
        self,
        interaction: discord.Interaction,
        *,
        target: IncomeTarget,
        user: str,
        quantity: int,
    ) -> None:
        from bot.activity_log import person_name
        from bot.tier_sync import schedule_member_tier_sync
        from services.economy import EconomyService
        from services.ratings import WorkerRatingService

        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Invalid channel.", ephemeral=True)
            return

        ctx = require_context(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        try:
            result = await EconomyService(ctx).record_income(
                channel_id=str(interaction.channel.id),
                target=target,
                user_id=user,
                quantity=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        schedule_member_tier_sync(interaction.guild, user, ctx)

        order = await OrderService(ctx).get_by_channel_id(str(interaction.channel.id))
        if not order:
            await safe_respond(interaction, content="❌ Order not found after income.", ephemeral=True)
            return

        await after_income_recorded(
            guild=interaction.guild,
            order_channel=interaction.channel,
            order=order,
            target=target,
            user_id=user,
            quantity=quantity,
            result=result,
            ctx=ctx,
            worker_ratings_serv=WorkerRatingService(ctx),
        )
        await safe_respond(interaction, content="✅ Income recorded successfully.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"Recorded {target} income for {person_name(interaction.guild, user)}: "
                f"{quantity:,}x {order.get('item_name')} in #{interaction.channel.name}"
            ),
        )

    async def handle_custom_order(
        self,
        interaction: discord.Interaction,
        *,
        customer: str,
        item_name: str,
        item_price: int,
        quantity: int,
    ) -> None:
        from bot.ui.orders import OrderConfirmView, customer_total_price

        if interaction.guild is None:
            return

        ctx = require_context(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        member = interaction.guild.get_member(int(customer)) if customer.isdigit() else None
        if member is None:
            await safe_respond(interaction, content="❌ Member not found.", ephemeral=True)
            return

        category = interaction.guild.get_channel(ctx.channels.new_orders_category)
        if not isinstance(category, discord.CategoryChannel):
            await safe_respond(
                interaction,
                content="❌ Order category channel is not configured properly.",
                ephemeral=True,
            )
            return

        total_price = item_price * quantity
        item_emoji = "🌟"
        order_serv = OrderService(ctx)

        async def on_confirm(inter: discord.Interaction) -> None:
            await safe_defer(inter, ephemeral=True)
            if inter.guild is None:
                return

            try:
                order = await order_serv.create_custom_order(
                    customer_id=str(member.id),
                    item_name=item_name,
                    item_price=item_price,
                    item_quantity=quantity,
                )
            except ValueError as exc:
                await safe_respond(inter, content=f"❌ {exc}", ephemeral=True)
                return

            try:
                channel = await self._publish_order_channel(
                    guild=inter.guild,
                    category=category,
                    order=order,
                    ctx=ctx,
                    order_serv=order_serv,
                )
            except Exception:
                await order_serv.cancel_order(order=order)
                await safe_respond(
                    inter,
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
                f"\n🎟 Donor coupon applied — saved 🪙 ***{total_price - total_display:,}***"
                if order.get("coupon_applied")
                else ""
            )
            await safe_respond(
                inter,
                content=(
                    "✅ **Custom Order Created**\n\n"
                    f"👤 Customer: ***{member.mention}***\n"
                    f"📦 Item: ***{item_emoji} {order['item_name']}***\n"
                    f"🔢 Quantity: 🏷 ***{order['item_quantity']:,}***\n"
                    f"💰 Total: 🪙 ***{total_display:,}***"
                    f"{coupon_note}\n\n"
                    f"📍 Channel: ***{channel.mention}***"
                ),
                ephemeral=True,
            )
            await log_activity(
                guild=inter.guild,
                ctx=ctx,
                member=interaction.user,
                action=(
                    f"Created custom order for {member.display_name}: "
                    f"{order['item_quantity']:,}x {order['item_name']} in #{channel.name}"
                ),
            )

        await safe_respond(
            interaction,
            content=(
                "📝 **Confirm Custom Order**\n\n"
                f"👤 Customer: {member.mention}\n"
                f"📦 Item: ***{item_emoji} {item_name}***\n"
                f"🔢 Quantity: 🏷 ***{quantity:,}***\n"
                f"💰 Price: 🪙 ***{item_price:,}***\n"
                f"💰 Total: 🪙 ***{total_price:,}***"
            ),
            view=OrderConfirmView(on_confirm=on_confirm),
            ephemeral=True,
        )

    async def handle_update_price(self, interaction: discord.Interaction, *, new_price: int) -> None:
        from bot.ui.orders import order_update_embed

        channel, ctx, order = await self._require_order_channel(interaction)
        if channel is None or ctx is None or order is None:
            return
        if interaction.guild is None:
            return

        old_price = order["item_price"]
        try:
            updated = await OrderService(ctx).update_price(order=order, new_price=new_price)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await refresh_order_embed(channel=channel, order=updated, ctx=ctx)
        worker_role = interaction.guild.get_role(ctx.roles.worker)
        content, embed = order_update_embed(
            field="price",
            old_value=old_price,
            new_value=new_price,
            worker_role=worker_role,
            ctx=ctx,
        )
        await channel.send(content=content, embed=embed)
        await safe_respond(interaction, content="✅ Order item price updated.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"Changed order price from {old_price:,} to {new_price:,} gold "
                f"for {updated.get('item_name')} in #{channel.name}"
            ),
        )

    async def handle_update_quantity(
        self,
        interaction: discord.Interaction,
        *,
        mode: Literal["set", "add", "reduce"],
        quantity: int,
    ) -> None:
        from bot.ui.orders import order_update_embed

        channel, ctx, order = await self._require_order_channel(interaction)
        if channel is None or ctx is None or order is None:
            return
        if interaction.guild is None:
            return

        old_qty = order["item_quantity"]
        try:
            updated = await OrderService(ctx).update_quantity(
                order=order,
                mode=mode,
                quantity=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        new_qty = updated["item_quantity"]
        await refresh_order_embed(channel=channel, order=updated, ctx=ctx)

        safe_name = (
            f"{updated['item_quantity']}-{updated['item_name']}".lower().replace(" ", "-")
        )[:90]
        new_name = f"【{updated['order_number']}-📦】{safe_name}"
        if channel.name != new_name:
            await channel.edit(name=new_name)

        worker_role = interaction.guild.get_role(ctx.roles.worker)
        content, embed = order_update_embed(
            field="quantity",
            old_value=old_qty,
            new_value=new_qty,
            worker_role=worker_role,
            ctx=ctx,
        )
        await channel.send(content=content, embed=embed)
        await safe_respond(interaction, content="✅ Order item quantity updated.", ephemeral=True)
        if mode == "add":
            action = (
                f"Added {quantity:,} to order quantity ({old_qty:,} → {new_qty:,}) "
                f"for {updated.get('item_name')} in #{channel.name}"
            )
        elif mode == "reduce":
            action = (
                f"Reduced order quantity by {quantity:,} ({old_qty:,} → {new_qty:,}) "
                f"for {updated.get('item_name')} in #{channel.name}"
            )
        else:
            action = (
                f"Set order quantity from {old_qty:,} to {new_qty:,} "
                f"for {updated.get('item_name')} in #{channel.name}"
            )
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=action,
        )

    async def handle_update_customer(self, interaction: discord.Interaction, *, customer: str) -> None:
        from bot.activity_log import person_name
        from bot.ui.orders import order_update_embed

        channel, ctx, order = await self._require_order_channel(interaction)
        if channel is None or ctx is None or order is None:
            return
        if interaction.guild is None:
            return

        if not interaction.guild.get_member(int(customer)) if customer.isdigit() else True:
            await safe_respond(interaction, content="❌ Customer must be a server member.", ephemeral=True)
            return

        old_customer_id = order["customer_id"]
        try:
            updated = await OrderService(ctx).update_customer(order=order, new_customer_id=customer)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await refresh_order_embed(channel=channel, order=updated, ctx=ctx)
        worker_role = interaction.guild.get_role(ctx.roles.worker)
        content, embed = order_update_embed(
            field="customer",
            old_value=old_customer_id,
            new_value=customer,
            worker_role=worker_role,
            ctx=ctx,
        )
        await channel.send(content=content, embed=embed)
        await safe_respond(interaction, content="✅ Order customer updated.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"Changed order customer from {person_name(interaction.guild, old_customer_id)} "
                f"to {person_name(interaction.guild, customer)} "
                f"for {updated.get('item_name')} in #{channel.name}"
            ),
        )

    async def handle_force_claim(
        self,
        interaction: discord.Interaction,
        *,
        worker_id: str,
        quantity: int,
    ) -> None:
        from bot.activity_log import person_name
        from bot.ui.orders import claim_log_embed

        channel, ctx, order = await self._require_order_channel(interaction)
        if channel is None or ctx is None or order is None:
            return
        if interaction.guild is None:
            return

        if order["customer_id"] == worker_id:
            await safe_respond(interaction, content="❌ Worker cannot claim his/her own order.", ephemeral=True)
            return

        try:
            updated = await OrderClaimService(ctx).force_claim(
                order_id=order["order_id"],
                worker_id=worker_id,
                qty=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await sync_order_category(channel=channel, order=updated, ctx=ctx)
        await refresh_order_embed(channel=channel, order=updated, ctx=ctx)

        log_channel = interaction.guild.get_channel(ctx.channels.claim_log)
        worker = interaction.guild.get_member(int(worker_id))
        if isinstance(log_channel, discord.TextChannel) and worker:
            emoji = await ItemService(ctx).get_item_emoji(order["item_id"])
            await log_channel.send(
                embed=claim_log_embed(
                    worker=worker,
                    item_name=order["item_name"],
                    item_emoji=emoji,
                    quantity=quantity,
                    channel=channel,
                    action="force_claim",
                    staff=interaction.user,
                    ctx=ctx,
                )
            )

        await safe_respond(interaction, content="⚠️ Force claim executed.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"Force claimed {quantity:,}x {order['item_name']} "
                f"for {person_name(interaction.guild, worker_id)} "
                f"in #{channel.name}"
            ),
            status="warning",
        )

    async def handle_force_unclaim(
        self,
        interaction: discord.Interaction,
        *,
        worker_id: str,
        quantity: int,
    ) -> None:
        from bot.activity_log import person_name
        from bot.ui.orders import claim_log_embed

        channel, ctx, order = await self._require_order_channel(interaction)
        if channel is None or ctx is None or order is None:
            return
        if interaction.guild is None:
            return

        try:
            updated = await OrderClaimService(ctx).force_unclaim(
                order_id=order["order_id"],
                worker_id=worker_id,
                qty=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await sync_order_category(channel=channel, order=updated, ctx=ctx)
        await refresh_order_embed(channel=channel, order=updated, ctx=ctx)

        log_channel = interaction.guild.get_channel(ctx.channels.claim_log)
        worker = interaction.guild.get_member(int(worker_id))
        if isinstance(log_channel, discord.TextChannel) and worker:
            emoji = await ItemService(ctx).get_item_emoji(order["item_id"])
            await log_channel.send(
                embed=claim_log_embed(
                    worker=worker,
                    item_name=order["item_name"],
                    item_emoji=emoji,
                    quantity=quantity,
                    channel=channel,
                    action="force_unclaim",
                    staff=interaction.user,
                    ctx=ctx,
                )
            )

        await safe_respond(interaction, content="⚠️ Force unclaim executed.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"Force unclaimed {quantity:,}x {order['item_name']} "
                f"from {person_name(interaction.guild, worker_id)} "
                f"in #{channel.name}"
            ),
            status="warning",
        )

    async def handle_cancel_order(self, ctx: commands.Context) -> None:
        from utils.confirm_view import ConfirmView
        from utils.prefix_feedback import failed

        if ctx.guild is None or not isinstance(ctx.channel, discord.TextChannel):
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            await failed(ctx)
            return

        order_serv = OrderService(tenant)
        order = await order_serv.get_by_channel_id(str(ctx.channel.id))
        if not order:
            await ctx.send("❌ This is not an order channel.", delete_after=5)
            await failed(ctx)
            return

        view = ConfirmView(author_id=ctx.author.id, timeout_seconds=30)
        prompt = await ctx.send(
            "⚠️ **Confirmation Required**\n\nAre you sure you want to **CANCEL** this order?",
            view=view,
        )
        confirmed = await view.wait_result()
        try:
            await prompt.edit(view=view)
        except discord.HTTPException:
            pass

        if not confirmed:
            await ctx.send("❌ Cancel aborted.", delete_after=5)
            await failed(ctx)
            return

        try:
            await order_serv.cancel_order(order=order)
        except ValueError as exc:
            await ctx.send(f"❌ {exc}", delete_after=5)
            await failed(ctx)
            return

        await log_activity(
            guild=ctx.guild,
            ctx=tenant,
            member=ctx.author,
            action=(
                f"Cancelled order #{order.get('order_number')} "
                f"({order.get('item_name')}) in #{ctx.channel.name}"
            ),
            status="cancelled",
        )
        await ctx.send("❌ Order canceled. Channel will be deleted.")
        await asyncio.sleep(5)
        await ctx.channel.delete(reason="Order canceled")

    async def handle_calculate_worker_payment(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        from bot.ui.calc_payment import CalcWorkerPaymentView
        from services.items import ItemService

        if interaction.guild is None:
            return
        ctx = require_context(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        view = CalcWorkerPaymentView(
            ctx=ctx,
            order_serv=OrderService(ctx),
            item_serv=ItemService(ctx),
            source_message=message,
            guild=interaction.guild,
            claimed_category_id=ctx.channels.claimed_orders_category,
        )
        await view.order_select.load()
        await safe_respond(
            interaction,
            content="🧮 **Calculate Worker Payment**",
            view=view,
            ephemeral=True,
        )

    async def _publish_order_channel(
        self,
        *,
        guild: discord.Guild,
        category: discord.CategoryChannel,
        order: dict,
        ctx: GameContext,
        order_serv: OrderService,
    ) -> discord.TextChannel:
        from bot.ui.orders import OrderClaimView, order_embed

        safe_name = (f"{order['item_quantity']}-{order['item_name']}".lower().replace(" ", "-"))[:90]
        channel = await guild.create_text_channel(
            name=f"【{order['order_number']}-📦】{safe_name}",
            category=category,
        )
        content, embed = order_embed(order=order, ctx=ctx, guild=guild)
        worker_role = guild.get_role(ctx.roles.worker)
        msg = await channel.send(
            content=content,
            embed=embed,
            view=OrderClaimView(),
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=[worker_role] if worker_role else False,
            ),
        )
        await order_serv.set_channel_and_message(
            order_id=order["order_id"],
            channel_id=str(channel.id),
            message_id=msg.id,
        )
        return channel

    async def _require_order_channel(
        self,
        interaction: discord.Interaction,
    ) -> tuple[discord.TextChannel | None, GameContext | None, dict | None]:
        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Must be used in an order channel.", ephemeral=True)
            return None, None, None
        ctx = require_context(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return None, None, None
        order = await OrderService(ctx).get_by_channel_id(str(interaction.channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return None, None, None
        return interaction.channel, ctx, order


_handler: OrderHandler | None = None


def get_order_handler() -> OrderHandler:
    global _handler
    if _handler is None:
        _handler = OrderHandler()
    return _handler
