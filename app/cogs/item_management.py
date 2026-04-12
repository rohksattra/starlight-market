# app/cogs/item_management.py
from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands

from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.services.item_service import ItemService
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown


if TYPE_CHECKING:
    from app.cogs.item_management import ItemManagement


async def category_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    bot = cast(commands.Bot, interaction.client)
    cog = cast("ItemManagement", bot.get_cog("ItemManagement"))
    if cog is None:
        return []
    categories = await cog.item_serv.list_categories()
    return [app_commands.Choice(name=c, value=c) for c in categories if current.lower() in c.lower()][:25]


async def item_by_category_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    bot = cast(commands.Bot, interaction.client)
    cog = cast("ItemManagement", bot.get_cog("ItemManagement"))
    if cog is None:
        return []
    category = getattr(interaction.namespace, "category", None)
    if not category:
        return []
    items = await cog.item_serv.list_items_by_category(category)
    return [app_commands.Choice(name=i["item_name"], value=i["item_id"]) for i in items if current.lower() in i["item_name"].lower()][:25]


class ItemManagement(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.item_serv = ItemService()

    def _is_staff(self, member: discord.Member) -> bool:
        return has_any_role(member, ORDER_MANAGEMENT_ROLES)

    @app_commands.command(name="update-category-name", description="(Staff) Update category name")
    @app_commands.autocomplete(category=category_autocomplete)
    async def update_category_name(self, interaction: discord.Interaction, category: str, new_category_name: str) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return
        try:
            check_cooldown(user_id=interaction.user.id, key="update_category", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        if not self._is_staff(interaction.user):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return
        try:
            await self.item_serv.update_category_name(old_name=category, new_name=new_category_name)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        await safe_respond(interaction, content=f"✅ Category **{category}** renamed to **{new_category_name.strip()}**.", ephemeral=True)

    @app_commands.command(name="update-item-name", description="(Staff) Update item name")
    @app_commands.autocomplete(category=category_autocomplete, item_id=item_by_category_autocomplete)
    async def update_item_name(self, interaction: discord.Interaction, category: str, item_id: str, new_name: str) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return
        try:
            check_cooldown(user_id=interaction.user.id, key="update_item_name", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        if not self._is_staff(interaction.user):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return
        try:
            await self.item_serv.update_item_name(item_id=item_id, new_name=new_name)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        await safe_respond(interaction, content="✅ Item name updated.", ephemeral=True)

    @app_commands.command(name="update-item-price", description="(Staff) Update item price")
    @app_commands.autocomplete(category=category_autocomplete, item_id=item_by_category_autocomplete)
    async def update_item_price(self, interaction: discord.Interaction, category: str, item_id: str, new_price: int) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return
        try:
            check_cooldown(user_id=interaction.user.id, key="update_item_price", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        if not self._is_staff(interaction.user):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return
        try:
            await self.item_serv.update_price(item_id, new_price)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        await safe_respond(interaction, content="✅ Item price updated.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ItemManagement(bot))