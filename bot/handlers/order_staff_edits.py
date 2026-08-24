"""Staff order edits: custom order, price, quantity, customer."""
from __future__ import annotations

import logging
from typing import Literal

import discord

from bot.activity_log import log_activity
from bot.handlers.order_presenters import refresh_order_embed, require_context
from services.orders import OrderService
from utils.discord_safe import safe_defer, safe_respond

log = logging.getLogger("bot.handlers.order_staff")


class OrderStaffEditsMixin:
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
                log.exception("Failed to create custom order channel")
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
