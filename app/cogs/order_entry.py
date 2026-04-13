# app/cogs/order_entry.py
from __future__ import annotations

import discord
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role, has_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES, ServerRole
from app.services.item_service import ItemService
from app.services.order_service import OrderService
from app.uis.order_category_view import OrderCategoryView
from app.uis.order_confirm_view import OrderConfirmView
from app.uis.order_embed import order_embed
from app.uis.order_entry_embed import order_entry_embed
from app.uis.order_entry_view import OrderEntryView
from app.uis.order_item_view import OrderItemView
from app.uis.order_quantity_view import QuantityModal
from utils.command_prefix_feedback import failed, success
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown


class OrderEntry(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.item_serv = ItemService()
        self.order_serv = OrderService()
        self.bot.add_view(OrderEntryView(self.start_order))

    async def start_order(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member):
            return
        if interaction.guild is None:
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="start_order", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        if not has_role(interaction.user, ServerRole.CUSTOMER):
            await safe_respond(interaction, content="❌ Only **Customers** can create orders.", ephemeral=True)
            return

        category_channel = interaction.guild.get_channel(settings.NEW_ORDERS_CATEGORY_ID)
        if not isinstance(category_channel, discord.CategoryChannel):
            await safe_respond(interaction, content="❌ Order category channel is not configured properly.", ephemeral=True)
            return

        categories = await self.item_serv.list_categories()
        if not categories:
            await safe_respond(interaction, content="❌ No item categories available.", ephemeral=True)
            return

        async def on_category(inter: discord.Interaction, category: str) -> None:
            items = await self.item_serv.list_items_by_category(category)
            if not items:
                await safe_respond(inter, content="❌ No items found in this category.", ephemeral=True)
                return

            async def on_item(inter2: discord.Interaction, item_id: str) -> None:
                if inter2.response.is_done():
                    return

                item = next((i for i in items if i["item_id"] == item_id), None)
                if item is None:
                    await safe_respond(inter2, content="❌ Item not found.", ephemeral=True)
                    return

                item_emoji = item.get("item_emoji", "🌟")

                async def on_quantity(inter3: discord.Interaction, qty: int) -> None:
                    await safe_defer(inter3, ephemeral=True)

                    total_price = item["item_price"] * qty

                    async def on_confirm(inter4: discord.Interaction) -> None:
                        await safe_defer(inter4, ephemeral=True)

                        try:
                            order = await self.order_serv.create_order(
                                customer_id=str(inter4.user.id),
                                item_id=item["item_id"],
                                quantity=qty,
                            )
                        except ValueError as exc:
                            await safe_respond(inter4, content=f"❌ {exc}", ephemeral=True)
                            return

                        guild = inter4.guild
                        if guild is None:
                            return

                        safe_name = (f"{order['item_quantity']}-{order['item_name']}".lower().replace(" ", "-"))[:90]

                        channel = await guild.create_text_channel(
                            name=f"【{order['order_number']}-📦】{safe_name}",
                            category=category_channel,
                        )

                        content, embed = order_embed(
                            order=order,
                            worker_role_id=settings.WORKER_ROLE_ID,
                            guild=guild,
                        )

                        msg = await channel.send(content=content, embed=embed)

                        await self.order_serv.set_channel_and_message(
                            order_id=order["order_id"],
                            channel_id=str(channel.id),
                            message_id=msg.id,
                        )

                        await safe_respond(
                            inter4,
                            content=(
                                "✅ **Order Created**\n\n"
                                f"📦 Item: ***{item_emoji} {order['item_name']}***\n"
                                f"🔢 Quantity: 🏷 ***{order['item_quantity']:,}***\n"
                                f"💰 Total: 🪙 ***{order['item_price'] * order['item_quantity']:,}***\n\n"
                                f"📍 Channel: ***{channel.mention}***"
                            ),
                            ephemeral=True,
                        )

                    await safe_respond(
                        inter3,
                        content=(
                            "📝 **Confirm Order**\n\n"
                            f"📦 Item: ***{item_emoji} {item['item_name']}***\n"
                            f"🔢 Quantity: 🏷 ***{qty:,}***\n"
                            f"💰 Price: 🪙 ***{item['item_price']:,}***\n"
                            f"💰 Total: 🪙 ***{total_price:,}***"
                        ),
                        view=OrderConfirmView(on_confirm=on_confirm),
                        ephemeral=True,
                    )

                await inter2.response.send_modal(QuantityModal(on_submit=on_quantity))

            await safe_respond(
                inter,
                content="📦 Select item:",
                view=OrderItemView(
                    user_id=inter.user.id,
                    items=items,
                    page=0,
                    page_size=20,
                    on_pick=on_item,
                ),
                ephemeral=True,
            )

        await safe_respond(
            interaction,
            content="📂 Select category:",
            view=OrderCategoryView(
                user_id=interaction.user.id,
                categories=categories,
                page=0,
                page_size=20,
                on_select=on_category,
            ),
            ephemeral=True,
        )

    @commands.command(name="order")
    async def order_entry_panel(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member):
            return
        if ctx.guild is None:
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="order_panel", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return

        if not has_any_role(ctx.author, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Staff only.", delete_after=5)
            await failed(ctx)
            return

        channel = ctx.guild.get_channel(settings.PLACE_ORDER_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Place order channel not found.", delete_after=5)
            await failed(ctx)
            return

        role = ctx.guild.get_role(settings.BANK_MANAGER_ROLE_ID)
        role_mention = role.mention if role else "@Bank Manager"

        await channel.send(
            embed=order_entry_embed(role_mention),
            view=OrderEntryView(self.start_order),
        )

        await success(ctx)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrderEntry(bot))