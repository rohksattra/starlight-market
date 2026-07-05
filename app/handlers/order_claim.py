from __future__ import annotations

from typing import Literal

import discord

from core.config import settings
from core.role_map import has_role
from app.discord.order_presenter import refresh_order_embed, sync_order_category
from app.domains.enums.order_status_enum import OrderStatus
from app.domains.enums.role_enum import ServerRole
from app.services.item_service import ItemService
from app.services.order_claim_service import OrderClaimService
from app.services.order_service import OrderService
from app.views.claim_embed import claim_log_embed
from utils.interaction_safe import safe_defer, safe_respond


ClaimAction = Literal["claim", "unclaim", "force_claim", "force_unclaim"]


class OrderClaimHandler:
    def __init__(self) -> None:
        self.order_serv = OrderService()
        self.order_claim_serv = OrderClaimService()
        self.item_serv = ItemService()

    async def _get_order(self, channel: discord.TextChannel) -> dict | None:
        return await self.order_serv.get_by_channel_id(str(channel.id))

    async def _send_log(
        self,
        *,
        interaction: discord.Interaction,
        order: dict,
        quantity: int,
        action: ClaimAction,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        if not isinstance(interaction.user, discord.Member):
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            return

        log_channel = guild.get_channel(settings.CLAIM_MESSAGE_CHANNEL_ID)
        if not isinstance(log_channel, discord.TextChannel):
            return

        emoji = await self.item_serv.get_item_emoji(order["item_id"])

        embed = claim_log_embed(
            worker=interaction.user,
            item_name=order["item_name"],
            item_emoji=emoji,
            quantity=quantity,
            channel=interaction.channel,
            action=action,
        )

        await log_channel.send(embed=embed)

    async def handle_claim_refresh(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            return
        order = await self._get_order(interaction.channel)
        if not order:
            return
        await refresh_order_embed(channel=interaction.channel, order=order)

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
            await safe_respond(interaction, content="❌ This action must be used in an order channel.", ephemeral=True)
            return
        if not has_role(interaction.user, ServerRole.WORKER):
            await safe_respond(interaction, content="❌ Only **Workers** can use this action.", ephemeral=True)
            return

        order = await self._get_order(interaction.channel)
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return

        worker_id = str(interaction.user.id)
        if order["customer_id"] == worker_id:
            await safe_respond(interaction, content="❌ You cannot claim your own order.", ephemeral=True)
            return

        if action == "claim":
            try:
                updated = await self.order_claim_serv.claim(order_id=order["order_id"], worker_id=worker_id, qty=quantity)
            except ValueError as exc:
                await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
                return
            await sync_order_category(channel=interaction.channel, order=updated)
            await refresh_order_embed(channel=interaction.channel, order=updated)
            await self._send_log(interaction=interaction, order=updated, quantity=quantity, action="claim")
            await safe_respond(interaction, content=f"✅ Claimed ***{quantity:,}*** item(s).", ephemeral=True)
            return

        try:
            updated = await self.order_claim_serv.unclaim(order_id=order["order_id"], worker_id=worker_id, qty=quantity)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        await sync_order_category(channel=interaction.channel, order=updated)
        await refresh_order_embed(channel=interaction.channel, order=updated)
        await self._send_log(interaction=interaction, order=updated, quantity=quantity, action="unclaim")
        await safe_respond(interaction, content=f"✅ Unclaimed ***{quantity:,}*** item(s).", ephemeral=True)


_handler: OrderClaimHandler | None = None


def get_order_claim_handler() -> OrderClaimHandler:
    global _handler
    if _handler is None:
        _handler = OrderClaimHandler()
    return _handler
