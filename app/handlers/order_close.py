from __future__ import annotations

import asyncio
import logging

import discord

from core.role_map import has_role
from app.domains.enums.order_status_enum import OrderStatus
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.services.order_service import OrderService
from utils.cooldown import check_cooldown
from utils.interaction_safe import safe_respond


log = logging.getLogger("handlers.order_close")


class OrderCloseHandler:
    def __init__(self) -> None:
        self.order_serv = OrderService()

    async def handle_close_order_button(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid user.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="close_order", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        if not any(has_role(interaction.user, r) for r in ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Must be used in an order channel.", ephemeral=True)
            return

        order = await self.order_serv.get_by_channel_id(str(interaction.channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return

        if order["order_status"] != OrderStatus.DELIVERED:
            await safe_respond(interaction, content="❌ Only delivered orders can be closed.", ephemeral=True)
            return

        from app.views.order_close_view import OrderCloseConfirmView

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
        order = await self.order_serv.get_by_channel_id(str(channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return

        if order["order_status"] != OrderStatus.DELIVERED:
            await safe_respond(interaction, content="❌ Only delivered orders can be closed.", ephemeral=True)
            return

        try:
            await self.order_serv.close_order(order=order)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await channel.send("✅ Order closed. Channel will be deleted.")
        await asyncio.sleep(5)
        await channel.delete(reason="Order closed")


_handler: OrderCloseHandler | None = None


def get_order_close_handler() -> OrderCloseHandler:
    global _handler
    if _handler is None:
        _handler = OrderCloseHandler()
    return _handler
