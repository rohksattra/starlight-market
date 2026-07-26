from __future__ import annotations

from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES

from app.services.manual_income_service import ManualIncomeService
from app.services.item_service import ItemService
from app.discord.tier_role_sync import schedule_member_tier_sync

from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown
from utils.autocomplete import fallback_user_label, user_autocomplete
from utils.confirm_view import ConfirmView


class ManualIncome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = ManualIncomeService()
        self.item_serv = ItemService()

    def _is_allowed(self, member: discord.Member) -> bool:
        return has_any_role(member, ORDER_MANAGEMENT_ROLES)

    async def item_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        items = await self.item_serv.list_items()

        results = []

        for i in items:
            name = i.get("item_name", "")

            if current.lower() in name.lower():
                results.append(
                    app_commands.Choice(
                        name=name[:100],
                        value=i["item_id"],
                    )
                )

            if len(results) >= 25:
                break

        return results

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

        item_doc = await self.item_serv.get_by_id(item)
        if not item_doc:
            await safe_respond(interaction, content="❌ Item not found.", ephemeral=True)
            return

        member = interaction.guild.get_member(int(user)) if user.isdigit() else None
        user_label = member.display_name if member else fallback_user_label(user)
        item_name = item_doc.get("item_name", item)

        confirm_embed = discord.Embed(
            title="Confirm Paid",
            description=(
                "Please review the details below.\n"
                "Click **Confirm** to record worker income, or **Cancel**."
            ),
            color=0xFFD700,
        )
        confirm_embed.add_field(name="Worker", value=user_label, inline=True)
        confirm_embed.add_field(name="Item", value=item_name, inline=True)
        confirm_embed.add_field(name="Quantity", value=str(quantity), inline=True)

        view = ConfirmView(author_id=interaction.user.id, timeout_seconds=30)
        await safe_respond(interaction, embed=confirm_embed, view=view, ephemeral=True)

        confirmed = await view.wait_result()
        if not confirmed:
            await safe_respond(interaction, content="❌ Paid cancelled.", ephemeral=True)
            return

        try:
            result = await self.service.paid_worker(
                user_id=user,
                item_id=item,
                quantity=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        schedule_member_tier_sync(interaction.guild, user)

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

        item_doc = await self.item_serv.get_by_id(item)
        if not item_doc:
            await safe_respond(interaction, content="❌ Item not found.", ephemeral=True)
            return

        member = interaction.guild.get_member(int(user)) if user.isdigit() else None
        user_label = member.display_name if member else fallback_user_label(user)
        item_name = item_doc.get("item_name", item)

        confirm_embed = discord.Embed(
            title="Confirm Spent",
            description=(
                "Please review the details below.\n"
                "Click **Confirm** to record customer spending, or **Cancel**."
            ),
            color=0xFFD700,
        )
        confirm_embed.add_field(name="Customer", value=user_label, inline=True)
        confirm_embed.add_field(name="Item", value=item_name, inline=True)
        confirm_embed.add_field(name="Quantity", value=str(quantity), inline=True)

        view = ConfirmView(author_id=interaction.user.id, timeout_seconds=30)
        await safe_respond(interaction, embed=confirm_embed, view=view, ephemeral=True)

        confirmed = await view.wait_result()
        if not confirmed:
            await safe_respond(interaction, content="❌ Spent cancelled.", ephemeral=True)
            return

        try:
            result = await self.service.spent_customer(
                user_id=user,
                item_id=item,
                quantity=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        schedule_member_tier_sync(interaction.guild, user)

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