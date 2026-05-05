from __future__ import annotations

from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES

from app.services.manual_income_service import ManualIncomeService
from app.repositories.user_repo import UserRepository
from app.repositories.item_repo import ItemRepository

from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown


class ManualIncome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = ManualIncomeService()
        self.users = UserRepository()
        self.items = ItemRepository()

    def _is_allowed(self, member: discord.Member) -> bool:
        return has_any_role(member, ORDER_MANAGEMENT_ROLES)

    async def user_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        if not current or interaction.guild is None:
            return []

        docs = await self.users.users.find({"user_id": {"$regex": current}}, {"user_id": 1}).to_list(50)

        results = []
        for d in docs:
            uid = d.get("user_id")
            if not uid:
                continue

            try:
                member = interaction.guild.get_member(int(uid))
            except (ValueError, TypeError):
                member = None

            if member:
                label = f"{member.display_name} (@{member.name}) [{uid}]"
            else:
                label = f"Unknown User [{uid}]"

            results.append(app_commands.Choice(name=label[:100], value=uid))

        return results[:25]

    async def item_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        items = await self.items.get_all()

        results = []
        for i in items:
            name = i.get("item_name", "")
            if current.lower() in name.lower():
                results.append(app_commands.Choice(name=name, value=i["item_id"]))

        return results[:25]

    @app_commands.command(name="paid", description="(Bot Manager) Add manual worker income")
    @app_commands.autocomplete(user=user_autocomplete, item=item_autocomplete)
    async def paid(self, interaction: discord.Interaction, user: str, item: str, quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid context.", ephemeral=True)
            return

        if not self._is_allowed(interaction.user):
            await safe_respond(interaction, content="❌ Only Bot Developer / Bank Manager.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="paid", seconds=3)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        try:
            result = await self.service.paid_worker(user_id=user, item_id=item, quantity=quantity)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await safe_respond(
            interaction,
            content=(
                f"✅ Paid recorded\n"
                f"User: `{result['user_id']}`\n"
                f"Item: {result['item_name']}\n"
                f"Qty: {result['quantity']}\n"
                f"Income: **{result['income']:,}**"
            ),
            ephemeral=True,
        )

    @app_commands.command(name="spent", description="(Bot Manager) Add manual customer spending")
    @app_commands.autocomplete(user=user_autocomplete, item=item_autocomplete)
    async def spent(self, interaction: discord.Interaction, user: str, item: str, quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid context.", ephemeral=True)
            return

        if not self._is_allowed(interaction.user):
            await safe_respond(interaction, content="❌ Only Bot Developer / Bank Manager.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="spent", seconds=3)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        try:
            result = await self.service.spent_customer(user_id=user, item_id=item, quantity=quantity)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await safe_respond(
            interaction,
            content=(
                f"✅ Spent recorded\n"
                f"User: `{result['user_id']}`\n"
                f"Item: {result['item_name']}\n"
                f"Qty: {result['quantity']}\n"
                f"Total: **{result['spent']:,}**"
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ManualIncome(bot))