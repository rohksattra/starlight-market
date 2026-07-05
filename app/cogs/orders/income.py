from __future__ import annotations

from typing import Dict, List, Literal, cast

import discord
from discord import app_commands
from discord.ext import commands

from core.role_map import has_any_role
from app.domains.enums.order_status_enum import OrderStatus
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.discord.order_presenter import after_income_recorded
from app.services.income_service import OrderIncomeService
from app.discord.tier_role_sync import schedule_member_tier_sync
from app.services.order_service import OrderService
from app.services.worker_rating_service import WorkerRatingService
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown
from utils.autocomplete import fallback_user_label


IncomeTarget = Literal["worker", "customer"]


class OrderIncome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.income_serv = OrderIncomeService()
        self.order_serv = OrderService()
        self.worker_ratings_serv = WorkerRatingService()

    def _is_staff(self, member: discord.Member) -> bool:
        return has_any_role(member, ORDER_MANAGEMENT_ROLES)

    async def user_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            return []

        order = await self.order_serv.get_by_channel_id(str(interaction.channel.id))
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
                if member:
                    label = f"{member.display_name} ({member.name})"
                else:
                    label = fallback_user_label(wid)

                if current_lower and current_lower not in label.lower() and current_lower not in wid:
                    continue

                results.append(app_commands.Choice(name=label[:100], value=str(wid)))

        elif target == "customer":
            cid = order.get("customer_id")
            if cid:
                member = interaction.guild.get_member(int(cid))
                if member:
                    label = f"{member.display_name} ({member.name})"
                else:
                    label = fallback_user_label(str(cid))

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
    @app_commands.autocomplete(user=user_autocomplete)
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

        if not self._is_staff(interaction.user):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Invalid channel.", ephemeral=True)
            return

        try:
            result = await self.income_serv.record_income(
                channel_id=str(interaction.channel.id),
                target=target,
                user_id=user,
                quantity=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        schedule_member_tier_sync(interaction.guild, user)

        order = await self.order_serv.get_by_channel_id(str(interaction.channel.id))
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
            worker_ratings_serv=self.worker_ratings_serv,
        )

        await safe_respond(interaction, content="✅ Income recorded successfully.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrderIncome(bot))
