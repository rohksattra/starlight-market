# app/cogs/transaction.py
from __future__ import annotations

from typing import Dict, List, Literal, cast

import discord
from discord import app_commands
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.order_status_enum import OrderStatus
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.services.transaction_service import TransactionService
from app.services.order_service import OrderService
from app.services.worker_rating_service import WorkerRatingService
from app.uis.order_close_embed import close_embed
from app.uis.order_embed import update_order_embed
from app.uis.pickup_embed import pickup_embed
from app.uis.transaction_embed import transaction_embed
from app.uis.worker_rating_button import RatingWorkerButton
from app.uis.worker_rating_embed import worker_rating_embed
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown


IncomeTarget = Literal["worker", "customer"]


class Income(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.transaction_serv = TransactionService()
        self.order_serv = OrderService()
        self.worker_ratings_serv = WorkerRatingService()

    def _is_staff(self, member: discord.Member) -> bool:
        return has_any_role(member, ORDER_MANAGEMENT_ROLES)

    async def user_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            return []
        order = await self.order_serv.get_by_channel_id(str(interaction.channel.id))
        if not order:
            return []
        if order["order_status"] not in {OrderStatus.NEW, OrderStatus.CLAIMED, OrderStatus.COMPLETED}:
            return []
        target = getattr(interaction.namespace, "target", None)
        results: List[app_commands.Choice[str]] = []
        if target == "worker":
            for wid in cast(Dict[str, int], order.get("worker_claims", {})):
                member = interaction.guild.get_member(int(wid))
                if member and current.lower() in member.display_name.lower():
                    results.append(app_commands.Choice(name=f"{member.display_name} ({member.name})", value=str(member.id)))
        elif target == "customer":
            cid = order.get("customer_id")
            if cid:
                member = interaction.guild.get_member(int(cid))
                if member:
                    results.append(app_commands.Choice(name=f"{member.display_name} ({member.name})", value=str(member.id)))
        return results[:25]

    @app_commands.command(name="income", description="(Staff) Record worker income or customer payment")
    @app_commands.choices(target=[app_commands.Choice(name="Worker", value="worker"), app_commands.Choice(name="Customer", value="customer")])
    @app_commands.autocomplete(user=user_autocomplete)
    async def income(self, interaction: discord.Interaction, target: IncomeTarget, user: str, quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid context.", ephemeral=True)
            return
        try:
            check_cooldown(user_id=interaction.user.id, key="income", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        if not self._is_staff(interaction.user):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Invalid channel.", ephemeral=True)
            return
        try:
            result = await self.transaction_serv.record_income(channel_id=str(interaction.channel.id), target=target, user_id=user, quantity=quantity)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        order = result["order"]
        guild = interaction.guild
        order_channel = interaction.channel
        member = guild.get_member(int(user))
        await update_order_embed(channel=order_channel, order=order, worker_role_id=settings.WORKER_ROLE_ID)
        tx_channel = guild.get_channel(settings.TRANSACTION_CHANNEL_ID)
        if isinstance(tx_channel, discord.TextChannel) and member:
            await tx_channel.send(embed=transaction_embed(role=target, member=member, order=order, quantity=quantity))
        if target == "worker" and member:
            rating_channel = guild.get_channel(settings.RATING_MESSAGE_CHANNEL_ID)
            if isinstance(rating_channel, discord.TextChannel):
                customer = guild.get_member(int(order["customer_id"]))
                if customer:
                    msg = await rating_channel.send(
                        embed=worker_rating_embed(
                            worker=member, customer=customer, item_name=order["item_name"], item_quantity=quantity, order_channel=order_channel,
                        ),
                        view=RatingWorkerButton(),
                    )
                    await self.worker_ratings_serv.request_rating(transaction_id=str(msg.id), worker_id=str(user), customer_id=str(customer.id))
        if target == "worker" and result.get("finished"):
            category = guild.get_channel(settings.COMPLETED_ORDERS_CATEGORY_ID)
            if isinstance(category, discord.CategoryChannel):
                await order_channel.edit(category=category)
            customer = guild.get_member(int(order["customer_id"]))
            if customer:
                await order_channel.send(
                    embed=pickup_embed(
                        customer_mention=customer.mention,
                        bank_manager_role_id=settings.BANK_MANAGER_ROLE_ID,
                        item_name=order["item_name"],
                        quantity=order["order_claims"]["order_completed"],
                        total_price=(order["order_claims"]["order_completed"] * order["item_price"]),
                    )
                )
        if target == "customer" and result.get("delivered"):
            await order_channel.send(
                embed=close_embed(bank_manager_role_id=settings.BANK_MANAGER_ROLE_ID),
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        await safe_respond(interaction, content="✅ Income recorded successfully.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Income(bot))
