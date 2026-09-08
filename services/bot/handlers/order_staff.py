"""Staff order mutations: income plus edit/force mixins."""
from __future__ import annotations

import logging

import discord

from bot.activity_log import log_activity
from bot.handlers.order_presenters import (
    IncomeTarget,
    after_income_recorded,
    require_context,
)
from bot.handlers.order_staff_edits import OrderStaffEditsMixin
from bot.handlers.order_staff_force import OrderStaffForceMixin
from core.tenant import GameContext
from services.orders import OrderService
from utils.discord_safe import safe_respond

log = logging.getLogger("bot.handlers.order_staff")


class OrderStaffMixin(OrderStaffEditsMixin, OrderStaffForceMixin):
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
