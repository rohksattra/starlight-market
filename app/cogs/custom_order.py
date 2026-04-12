# app/cogs/custom_order.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.services.order_service import OrderService
from app.uis.order_confirm_view import OrderConfirmView
from app.uis.order_embed import order_embed
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown


class CustomOrder(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.order_serv = OrderService()

    async def _autocomplete_member(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        current_lower = current.lower()
        choices: list[app_commands.Choice[str]] = []
        for member in interaction.guild.members:
            if member.bot:
                continue
            name = f"{member.display_name} ({member.name})"
            if current_lower in name.lower():
                choices.append(app_commands.Choice(name=name[:100], value=str(member.id)))
            if len(choices) >= 20:
                break
        return choices

    @app_commands.command(name="custom-order", description="(Staff) Create a custom/manual order for a member")
    @app_commands.describe(customer="Customer (server member)", item_name="Custom item name", item_price="Price per item", quantity="Item quantity")
    @app_commands.autocomplete(customer=_autocomplete_member)
    async def custom_order(self, interaction: discord.Interaction, customer: str, item_name: str, item_price: int, quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)
        if interaction.guild is None:
            return
        if not isinstance(interaction.user, discord.Member):
            return
        try:
            check_cooldown(user_id=interaction.user.id, key="custom_order", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        if not has_any_role(interaction.user, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return
        member = interaction.guild.get_member(int(customer))
        if member is None:
            await safe_respond(interaction, content="❌ Member not found.", ephemeral=True)
            return
        category = interaction.guild.get_channel(settings.NEW_ORDERS_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            await safe_respond(interaction, content="❌ Order category channel is not configured properly.", ephemeral=True)
            return
        total_price = item_price * quantity
        async def on_confirm(inter: discord.Interaction) -> None:
            await safe_defer(inter, ephemeral=True)
            if inter.guild is None:
                return
            try:
                order = await self.order_serv.create_custom_order(
                    customer_id=str(member.id), item_name=item_name, item_price=item_price, item_quantity=quantity,
                )
            except ValueError as exc:
                await safe_respond(inter, content=f"❌ {exc}", ephemeral=True)
                return
            try:
                safe_name = (f"{order['item_quantity']}-{order['item_name']}".lower().replace(" ", "-"))[:90]
                channel = await inter.guild.create_text_channel(name=f"【{order['order_number']}-📦】{safe_name}", category=category)
                content, embed = order_embed(
                    order=order, worker_role_id=settings.WORKER_ROLE_ID, guild=inter.guild,
                )
                msg = await channel.send(content=content, embed=embed)
                await self.order_serv.set_channel_and_message(order_id=order["order_id"], channel_id=str(channel.id), message_id=msg.id)
            except Exception:
                await self.order_serv.cancel_order(order=order)
                await safe_respond(inter, content=(
                        "❌ **Failed to create order channel.**\n"
                        "Order has been canceled automatically.\n"
                        "You can make it again."
                    ), ephemeral=True)
                return
            await safe_respond(inter, content=(
                    "✅ **Custom Order Created**\n\n"
                    f"👤 Customer: ***{member.mention}***\n"
                    f"📦 Item: ***{order['item_name']}***\n"
                    f"🔢 Quantity: 🏷 ***{order['item_quantity']:,}***\n"
                    f"💰 Total: 🪙 ***{total_price:,}***\n\n"
                    f"📍 Channel: ***{channel.mention}***"
                ), ephemeral=True)
        await safe_respond(interaction, content=(
                "📝 **Confirm Custom Order**\n\n"
                f"👤 Customer: {member.mention}\n"
                f"📦 Item: ***{item_name}***\n"
                f"🔢 Quantity: 🏷 ***{quantity:,}***\n"
                f"💰 Price: 🪙 ***{item_price:,}***\n"
                f"💰 Total: 🪙 ***{total_price:,}***"
            ), view=OrderConfirmView(on_confirm=on_confirm), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CustomOrder(bot))
