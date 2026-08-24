"""Staff force claim/unclaim, cancel, and payment calculator."""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from bot.activity_log import log_activity
from bot.handlers.order_presenters import refresh_order_embed, require_context, sync_order_category
from core.tenant import get_context
from services.items import ItemService
from services.order_claim import OrderClaimService
from services.orders import OrderService
from utils.discord_safe import safe_respond

log = logging.getLogger("bot.handlers.order_staff")


class OrderStaffForceMixin:
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
