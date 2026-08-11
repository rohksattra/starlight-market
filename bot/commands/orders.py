"""
Slash & prefix commands for order flow.
Thin layer: validate input → call service → send UI.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Literal, cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.activity_log import log_activity
from bot.handlers.orders import (
    after_income_recorded,
    get_order_handler,
    refresh_order_embed,
    sync_order_category,
)
from bot.tier_sync import schedule_member_tier_sync
from bot.ui.calc_payment import CalcWorkerPaymentView
from bot.ui.orders import (
    OrderCategoryView,
    OrderClaimView,
    OrderConfirmView,
    OrderEntryView,
    OrderItemView,
    QuantityModal,
    claim_log_embed,
    customer_total_price,
    order_embed,
    order_entry_embed,
    order_update_embed,
)
from bot.ui.shared import button_notice_content_suffix
from core.tenant import get_context
from models.enums import ORDER_MANAGEMENT_ROLES, OrderStatus, ServerRole
from services.economy import EconomyService
from services.items import ItemService
from services.order_claim import OrderClaimService
from services.orders import OrderService
from services.ratings import WorkerRatingService
from utils.autocomplete import fallback_user_label, user_autocomplete
from utils.confirm_view import ConfirmView
from utils.cooldown import check_cooldown
from utils.discord_safe import safe_defer, safe_respond
from utils.permissions import has_any_role, has_role
from utils.prefix_feedback import failed, success

IncomeTarget = Literal["worker", "customer"]


class OrderCommands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot.add_view(OrderEntryView(self.start_order))

        self.calc_worker_ctx = app_commands.ContextMenu(
            name="Calculate Worker Payment",
            callback=self.calculate_worker_payment,
        )
        old = self.bot.tree.get_command(
            "Calculate Worker Payment",
            type=discord.AppCommandType.message,
        )
        if old is not None:
            self.bot.tree.remove_command(
                "Calculate Worker Payment",
                type=discord.AppCommandType.message,
            )
        self.bot.tree.add_command(self.calc_worker_ctx)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.calc_worker_ctx.name,
            type=self.calc_worker_ctx.type,
        )

    async def start_order(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            return

        ctx = get_context(interaction.guild.id)
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

                        safe_name = (f"{order['item_quantity']}-{order['item_name']}".lower().replace(" ", "-"))[:90]

                        try:
                            channel = await guild.create_text_channel(
                                name=f"【{order['order_number']}-📦】{safe_name}",
                                category=category_channel,
                            )
                            content, embed = order_embed(order=order, ctx=ctx, guild=guild)
                            msg = await channel.send(content=content, embed=embed, view=OrderClaimView())
                            await order_serv.set_channel_and_message(
                                order_id=order["order_id"],
                                channel_id=str(channel.id),
                                message_id=msg.id,
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
                                f"create an order of {order['item_quantity']:,}x "
                                f"{order['item_name']} (#{channel.name})"
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

                await inter2.response.send_modal(QuantityModal(on_submit=on_quantity))

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

    @commands.command(name="order")
    async def order_entry_panel(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.guild is None:
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            await failed(ctx)
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="order_panel", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return

        if not has_any_role(ctx.author, tenant, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Staff only.", delete_after=5)
            await failed(ctx)
            return

        channel = ctx.guild.get_channel(tenant.channels.place_order)
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Place order channel not found.", delete_after=5)
            await failed(ctx)
            return

        role = ctx.guild.get_role(tenant.roles.bank_manager)
        role_mention = role.mention if role else "@Bank Manager"

        await channel.send(
            embed=order_entry_embed(role_mention),
            view=OrderEntryView(self.start_order),
        )
        await success(ctx)

    @app_commands.command(name="claim", description="(Worker) Claim items from this order")
    async def claim(self, interaction: discord.Interaction, quantity: int) -> None:
        try:
            check_cooldown(user_id=interaction.user.id, key="claim", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        await get_order_handler().handle_claim_action(interaction, action="claim", quantity=quantity)

    @app_commands.command(name="unclaim", description="(Worker) Cancel your claim")
    async def unclaim(self, interaction: discord.Interaction, quantity: int) -> None:
        try:
            check_cooldown(user_id=interaction.user.id, key="unclaim", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        await get_order_handler().handle_claim_action(interaction, action="unclaim", quantity=quantity)

    async def income_user_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            return []

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            return []

        order = await OrderService(ctx).get_by_channel_id(str(interaction.channel.id))
        if not order:
            return []

        if order["order_status"] not in {
            OrderStatus.NEW,
            OrderStatus.CLAIMED,
            OrderStatus.COMPLETED,
        }:
            return []

        target = getattr(interaction.namespace, "target", None)
        current_lower = current.lower()
        results: List[app_commands.Choice[str]] = []

        if target == "worker":
            for wid, qty in sorted(
                cast(Dict[str, int], order.get("worker_claims", {})).items(),
                key=lambda item: item[0],
            ):
                if qty <= 0:
                    continue
                member = interaction.guild.get_member(int(wid))
                label = (
                    f"{member.display_name} ({member.name})"
                    if member
                    else fallback_user_label(wid)
                )
                if current_lower and current_lower not in label.lower() and current_lower not in wid:
                    continue
                results.append(app_commands.Choice(name=label[:100], value=str(wid)))

        elif target == "customer":
            cid = order.get("customer_id")
            if cid:
                member = interaction.guild.get_member(int(cid))
                label = (
                    f"{member.display_name} ({member.name})"
                    if member
                    else fallback_user_label(str(cid))
                )
                if not current_lower or current_lower in label.lower() or current_lower in str(cid):
                    results.append(app_commands.Choice(name=label[:100], value=str(cid)))

        return results[:25]

    @app_commands.command(
        name="income",
        description="(Staff) Record worker income or customer payment",
    )
    @app_commands.choices(
        target=[
            app_commands.Choice(name="Worker", value="worker"),
            app_commands.Choice(name="Customer", value="customer"),
        ]
    )
    @app_commands.autocomplete(user=income_user_autocomplete)
    async def income(
        self,
        interaction: discord.Interaction,
        target: IncomeTarget,
        user: str,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid context.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="income", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Invalid channel.", ephemeral=True)
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
                f"record {target} income for {user} "
                f"qty {quantity:,} of {order.get('item_name')} "
                f"(#{interaction.channel.name})"
            ),
        )

    @app_commands.command(name="custom-order", description="(Staff) Create a custom/manual order for a member")
    @app_commands.describe(
        customer="Customer (server member)",
        item_name="Custom item name",
        item_price="Price per item",
        quantity="Item quantity",
    )
    @app_commands.autocomplete(customer=user_autocomplete)
    async def custom_order(
        self,
        interaction: discord.Interaction,
        customer: str,
        item_name: str,
        item_price: int,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="custom_order", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
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
                safe_name = (f"{order['item_quantity']}-{order['item_name']}".lower().replace(" ", "-"))[:90]
                channel = await inter.guild.create_text_channel(
                    name=f"【{order['order_number']}-📦】{safe_name}",
                    category=category,
                )
                content, embed = order_embed(order=order, ctx=ctx, guild=inter.guild)
                msg = await channel.send(content=content, embed=embed, view=OrderClaimView())
                await order_serv.set_channel_and_message(
                    order_id=order["order_id"],
                    channel_id=str(channel.id),
                    message_id=msg.id,
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
                    f"create a custom order for {member.name} {member.id} "
                    f"of {order['item_quantity']:,}x {order['item_name']} "
                    f"(#{channel.name})"
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

    @app_commands.command(name="order-item-price-update", description="(Staff) Update order item price")
    async def update_price(self, interaction: discord.Interaction, new_price: int) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="order_update_price", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Must be used in an order channel.", ephemeral=True)
            return

        order_serv = OrderService(ctx)
        order = await order_serv.get_by_channel_id(str(interaction.channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return

        old_price = order["item_price"]
        try:
            updated = await order_serv.update_price(order=order, new_price=new_price)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await refresh_order_embed(channel=interaction.channel, order=updated, ctx=ctx)
        worker_role = interaction.guild.get_role(ctx.roles.worker)
        content, embed = order_update_embed(
            field="price",
            old_value=old_price,
            new_value=new_price,
            worker_role=worker_role,
        )
        await interaction.channel.send(content=content, embed=embed)
        await safe_respond(interaction, content="✅ Order item price updated.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"update order price from {old_price:,} to {new_price:,} "
                f"for {updated.get('item_name')} (#{interaction.channel.name})"
            ),
        )

    @app_commands.command(name="order-item-quantity-update", description="(Staff) Update order item quantity")
    async def update_quantity(self, interaction: discord.Interaction, new_quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="order_update_quantity", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Must be used in an order channel.", ephemeral=True)
            return

        order_serv = OrderService(ctx)
        order = await order_serv.get_by_channel_id(str(interaction.channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return

        old_qty = order["item_quantity"]
        try:
            updated = await order_serv.update_quantity(order=order, new_quantity=new_quantity)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await refresh_order_embed(channel=interaction.channel, order=updated, ctx=ctx)

        safe_name = (
            f"{updated['item_quantity']}-{updated['item_name']}".lower().replace(" ", "-")
        )[:90]
        new_name = f"【{updated['order_number']}-📦】{safe_name}"
        if interaction.channel.name != new_name:
            await interaction.channel.edit(name=new_name)

        worker_role = interaction.guild.get_role(ctx.roles.worker)
        content, embed = order_update_embed(
            field="quantity",
            old_value=old_qty,
            new_value=new_quantity,
            worker_role=worker_role,
        )
        await interaction.channel.send(content=content, embed=embed)
        await safe_respond(interaction, content="✅ Order item quantity updated.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"update order quantity from {old_qty:,} to {new_quantity:,} "
                f"for {updated.get('item_name')} (#{interaction.channel.name})"
            ),
        )

    @app_commands.command(name="order-customer-update", description="(Staff) Change order customer")
    @app_commands.describe(customer="New customer (server member)")
    @app_commands.autocomplete(customer=user_autocomplete)
    async def update_customer(self, interaction: discord.Interaction, customer: str) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="order_update_customer", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Must be used in an order channel.", ephemeral=True)
            return

        if not interaction.guild.get_member(int(customer)) if customer.isdigit() else True:
            await safe_respond(interaction, content="❌ Customer must be a server member.", ephemeral=True)
            return

        order_serv = OrderService(ctx)
        order = await order_serv.get_by_channel_id(str(interaction.channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return

        old_customer_id = order["customer_id"]
        try:
            updated = await order_serv.update_customer(order=order, new_customer_id=customer)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await refresh_order_embed(channel=interaction.channel, order=updated, ctx=ctx)
        worker_role = interaction.guild.get_role(ctx.roles.worker)
        content, embed = order_update_embed(
            field="customer",
            old_value=old_customer_id,
            new_value=customer,
            worker_role=worker_role,
        )
        await interaction.channel.send(content=content, embed=embed)
        await safe_respond(interaction, content="✅ Order customer updated.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"update order customer from {old_customer_id} to {customer} "
                f"for {updated.get('item_name')} (#{interaction.channel.name})"
            ),
        )

    async def worker_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            return []

        worker_role = interaction.guild.get_role(ctx.roles.worker)
        if worker_role is None:
            return []

        current_lower = current.lower()
        choices: List[app_commands.Choice[str]] = []
        for member in sorted(worker_role.members, key=lambda m: m.display_name.lower()):
            if member.bot:
                continue
            if (
                current_lower
                and current_lower not in member.display_name.lower()
                and current_lower not in member.name.lower()
            ):
                continue
            choices.append(
                app_commands.Choice(
                    name=f"{member.display_name} ({member.name})"[:100],
                    value=str(member.id),
                )
            )
            if len(choices) >= 25:
                break
        return choices

    async def claimed_worker_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if not isinstance(interaction.channel, discord.TextChannel) or interaction.guild is None:
            return []

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            return []

        order = await OrderService(ctx).get_by_channel_id(str(interaction.channel.id))
        if not order:
            return []

        current_lower = current.lower()
        choices: List[app_commands.Choice[str]] = []
        for wid, qty in sorted(order.get("worker_claims", {}).items(), key=lambda item: item[0]):
            if qty <= 0:
                continue
            member = interaction.guild.get_member(int(wid))
            label = (
                f"{member.display_name} ({member.name}) — qty {qty}"
                if member
                else f"{fallback_user_label(wid)} — qty {qty}"
            )
            if current_lower and current_lower not in label.lower() and current_lower not in wid:
                continue
            choices.append(app_commands.Choice(name=label[:100], value=str(wid)))
            if len(choices) >= 25:
                break
        return choices

    @app_commands.command(name="force-claim", description="(Staff) Force claim to a worker")
    @app_commands.autocomplete(worker_id=worker_autocomplete)
    async def force_claim(
        self,
        interaction: discord.Interaction,
        worker_id: str,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="force_claim", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Must be used in an order channel.", ephemeral=True)
            return

        order_serv = OrderService(ctx)
        order = await order_serv.get_by_channel_id(str(interaction.channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
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

        await sync_order_category(channel=interaction.channel, order=updated, ctx=ctx)
        await refresh_order_embed(channel=interaction.channel, order=updated, ctx=ctx)

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
                    channel=interaction.channel,
                    action="force_claim",
                    staff=interaction.user,
                )
            )

        await safe_respond(interaction, content="⚠️ Force claim executed.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"force-claim {quantity:,}x {order['item_name']} "
                f"to worker {worker_id} (#{interaction.channel.name})"
            ),
        )

    @app_commands.command(name="force-unclaim", description="(Staff) Force unclaim to a worker")
    @app_commands.autocomplete(worker_id=claimed_worker_autocomplete)
    async def force_unclaim(
        self,
        interaction: discord.Interaction,
        worker_id: str,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="force_unclaim", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Must be used in an order channel.", ephemeral=True)
            return

        order_serv = OrderService(ctx)
        order = await order_serv.get_by_channel_id(str(interaction.channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
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

        await sync_order_category(channel=interaction.channel, order=updated, ctx=ctx)
        await refresh_order_embed(channel=interaction.channel, order=updated, ctx=ctx)

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
                    channel=interaction.channel,
                    action="force_unclaim",
                    staff=interaction.user,
                )
            )

        await safe_respond(interaction, content="⚠️ Force unclaim executed.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"force-unclaim {quantity:,}x {order['item_name']} "
                f"from worker {worker_id} (#{interaction.channel.name})"
            ),
        )

    @commands.command(name="cancel")
    async def cancel_order(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.guild is None:
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="cancel_order", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            await failed(ctx)
            return

        if not has_any_role(ctx.author, tenant, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Staff only.", delete_after=5)
            await failed(ctx)
            return

        if not isinstance(ctx.channel, discord.TextChannel):
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
                f"cancel order #{order.get('order_number')} "
                f"{order.get('item_name')} (#{ctx.channel.name})"
            ),
        )
        await ctx.send("❌ Order canceled. Channel will be deleted.")
        await asyncio.sleep(5)
        await ctx.channel.delete(reason="Order canceled")

    async def calculate_worker_payment(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="calc_worker_payment", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        tenant = get_context(interaction.guild.id)
        if tenant is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, tenant, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        view = CalcWorkerPaymentView(
            ctx=tenant,
            order_serv=OrderService(tenant),
            item_serv=ItemService(tenant),
            source_message=message,
            guild=interaction.guild,
            claimed_category_id=tenant.channels.claimed_orders_category,
        )
        await view.order_select.load()
        await safe_respond(
            interaction,
            content="🧮 **Calculate Worker Payment**",
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrderCommands(bot))
