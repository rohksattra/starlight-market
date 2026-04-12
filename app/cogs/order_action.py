# app/cogs/order_action.py
from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from core.config import settings
from core.role_map import has_role
from app.domains.enums.order_status_enum import OrderStatus
from app.domains.enums.role_enum import ServerRole
from app.services.order_claim_service import OrderClaimService
from app.services.order_service import OrderService
from app.uis.claim_embed import claim_log_embed
from app.uis.order_embed import update_order_embed
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown


ClaimAction = Literal["claim", "unclaim", "force_claim", "force_unclaim"]
MAX_ACTIVE_CLAIM = 6


class OrderActions(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.order_serv = OrderService()
        self.order_claim_serv = OrderClaimService()

    async def _get_order(self, channel: discord.TextChannel) -> dict | None:
        return await self.order_serv.get_by_channel_id(str(channel.id))

    async def _active_claim_count(self, worker_id: str) -> int:
        return await self.order_serv.count_active_by_worker(worker_id)

    async def _sync_category(self, *, channel: discord.TextChannel, order: dict) -> None:
        guild = channel.guild
        if guild is None:
            return
        if order["order_status"] not in {OrderStatus.NEW, OrderStatus.CLAIMED}:
            return
        claims = order["order_claims"]
        total = order["item_quantity"]
        target_category_id = (settings.NEW_ORDERS_CATEGORY_ID if claims["order_claimable"] == total else settings.CLAIMED_ORDERS_CATEGORY_ID)
        category = guild.get_channel(target_category_id)
        if isinstance(category, discord.CategoryChannel):
            await channel.edit(category=category)

    async def _send_log(self, *, interaction: discord.Interaction, order: dict, quantity: int, action: ClaimAction) -> None:
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

        embed = claim_log_embed(
            worker=interaction.user,
            item_name=order["item_name"],
            item_emoji=order.get("item_emoji", "🌟"),  # 🔥 FIX
            quantity=quantity,
            channel=interaction.channel,
            action=action
        )

        await log_channel.send(embed=embed)

    @app_commands.command(name="claim", description="(Worker) Claim items from this order")
    async def claim(self, interaction: discord.Interaction, quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return
        try:
            check_cooldown(user_id=interaction.user.id, key="claim", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        if not has_role(interaction.user, ServerRole.WORKER):
            await safe_respond(interaction, content="❌ Only **Workers** can use this command.", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ This command must be used in an order channel.", ephemeral=True)
            return
        order = await self._get_order(interaction.channel)
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return
        worker_id = str(interaction.user.id)
        if order["customer_id"] == worker_id:
            await safe_respond(interaction, content="❌ You cannot claim your own order.", ephemeral=True)
            return
        already_claimed = order.get("worker_claims", {}).get(worker_id, 0) > 0
        if not already_claimed:
            active = await self._active_claim_count(worker_id)
            if active >= MAX_ACTIVE_CLAIM:
                await safe_respond(interaction, content=f"❌ Claim limit reached (**{active}/{MAX_ACTIVE_CLAIM}**).", ephemeral=True)
                return
        try:
            updated = await self.order_claim_serv.claim(order_id=order["order_id"], worker_id=worker_id, qty=quantity)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        await self._sync_category(channel=interaction.channel, order=updated)
        await update_order_embed(channel=interaction.channel, order=updated, worker_role_id=settings.WORKER_ROLE_ID)
        await self._send_log(interaction=interaction, order=updated, quantity=quantity, action="claim")
        await safe_respond(interaction, content=f"✅ Claimed ***{quantity:,}*** item(s).", ephemeral=True)

    @app_commands.command(name="unclaim", description="(Worker) Cancel your claim")
    async def unclaim(self, interaction: discord.Interaction, quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return
        try:
            check_cooldown(user_id=interaction.user.id, key="unclaim", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        if not has_role(interaction.user, ServerRole.WORKER):
            await safe_respond(interaction, content="❌ Only **Workers** can use this command.", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ This command must be used in an order channel.", ephemeral=True)
            return
        order = await self._get_order(interaction.channel)
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return
        try:
            updated = await self.order_claim_serv.unclaim(order_id=order["order_id"], worker_id=str(interaction.user.id), qty=quantity)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        await self._sync_category(channel=interaction.channel, order=updated)
        await update_order_embed(channel=interaction.channel, order=updated, worker_role_id=settings.WORKER_ROLE_ID)
        await self._send_log(interaction=interaction, order=updated, quantity=quantity, action="unclaim")
        await safe_respond(interaction, content=f"✅ Unclaimed ***{quantity:,}*** item(s).", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrderActions(bot))