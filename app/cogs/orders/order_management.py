from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from core.config import settings
from core.role_map import has_role
from app.domains.enums.order_status_enum import OrderStatus
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.services.item_service import ItemService
from app.services.order_claim_service import OrderClaimService
from app.services.order_service import OrderService
from app.views.calculate_worker_payment_view import CalcWorkerPaymentView
from app.views.claim_embed import claim_log_embed
from app.views.order_embed import update_order_embed
from app.views.order_update_embed import order_update_embed
from utils.autocomplete import fallback_user_label, user_autocomplete
from utils.cooldown import check_cooldown
from utils.interaction_safe import safe_defer, safe_respond
from app.discord.order_presenter import sync_order_category
from app.handlers.order_close import get_order_close_handler


async def worker_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    guild = interaction.guild
    if guild is None:
        return []

    worker_role = guild.get_role(settings.WORKER_ROLE_ID)
    if worker_role is None:
        return []

    current_lower = current.lower()

    choices: list[app_commands.Choice[str]] = []

    for member in sorted(worker_role.members, key=lambda m: m.display_name.lower()):
        if member.bot:
            continue

        if current_lower and current_lower not in member.display_name.lower() and current_lower not in member.name.lower():
            continue

        choices.append(
            app_commands.Choice(
                name=f"{member.display_name} ({member.name})"[:100],
                value=str(member.id),
            )
        )

        if len(choices) >= 25:
            break

    return choices


async def claimed_worker_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not isinstance(interaction.channel, discord.TextChannel):
        return []

    guild = interaction.guild
    if guild is None:
        return []

    order = await OrderService().get_by_channel_id(str(interaction.channel.id))
    if not order:
        return []

    current_lower = current.lower()

    choices: list[app_commands.Choice[str]] = []

    for wid, qty in sorted(order.get("worker_claims", {}).items(), key=lambda item: item[0]):
        if qty <= 0:
            continue

        member = guild.get_member(int(wid))
        if member:
            label = f"{member.display_name} ({member.name}) — qty {qty}"
        else:
            label = f"{fallback_user_label(wid)} — qty {qty}"

        if current_lower and current_lower not in label.lower() and current_lower not in wid:
            continue

        choices.append(
            app_commands.Choice(
                name=label[:100],
                value=str(wid),
            )
        )

        if len(choices) >= 25:
            break

    return choices


class OrderManagement(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.order_serv = OrderService()
        self.order_claim_serv = OrderClaimService()
        self.item_serv = ItemService()
        self.close_handler = get_order_close_handler()

        self.calc_worker_ctx = app_commands.ContextMenu(
            name="Calculate Worker Payment",
            callback=self.calculate_worker_payment,
        )

        old_command = self.bot.tree.get_command(
            "Calculate Worker Payment",
            type=discord.AppCommandType.message,
        )

        if old_command is not None:
            self.bot.tree.remove_command(
                "Calculate Worker Payment",
                type=discord.AppCommandType.message,
            )

        self.bot.tree.add_command(self.calc_worker_ctx)

    async def _confirm(self, ctx: commands.Context, *, question: str) -> bool:
        await ctx.send(
            f"⚠️ **Confirmation Required**\n\n{question}\n\nReply with **Yes** or **No**.",
            delete_after=60,
        )

        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=30,
                check=check,
            )
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Confirmation timed out.", delete_after=5)
            return False

        return msg.content.lower() in {"yes", "y"}

    async def _get_item_emoji(self, item_id: str) -> str:
        return await self.item_serv.get_item_emoji(item_id)

    @app_commands.command(name="order-item-price-update", description="(Staff) Update order item price")
    async def update_price(self, interaction: discord.Interaction, new_price: int) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member):
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="order_update_price", seconds=5)
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

        old_price = order["item_price"]

        try:
            updated = await self.order_serv.update_price(order=order, new_price=new_price)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await update_order_embed(
            channel=interaction.channel,
            order=updated,
            worker_role_id=settings.WORKER_ROLE_ID,
        )

        worker_role = interaction.guild.get_role(settings.WORKER_ROLE_ID) if interaction.guild else None

        content, embed = order_update_embed(
            field="price",
            old_value=old_price,
            new_value=new_price,
            worker_role=worker_role,
        )

        await interaction.channel.send(content=content, embed=embed)
        await safe_respond(interaction, content="✅ Order item price updated.", ephemeral=True)

    @app_commands.command(name="order-item-quantity-update", description="(Staff) Update order item quantity")
    async def update_quantity(self, interaction: discord.Interaction, new_quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member):
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="order_update_quantity", seconds=5)
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

        old_qty = order["item_quantity"]

        try:
            updated = await self.order_serv.update_quantity(order=order, new_quantity=new_quantity)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await update_order_embed(
            channel=interaction.channel,
            order=updated,
            worker_role_id=settings.WORKER_ROLE_ID,
        )

        safe_name = (
            f"{updated['item_quantity']}-{updated['item_name']}"
            .lower()
            .replace(" ", "-")
        )[:90]
        new_name = f"【{updated['order_number']}-📦】{safe_name}"

        if interaction.channel.name != new_name:
            await interaction.channel.edit(name=new_name)

        worker_role = interaction.guild.get_role(settings.WORKER_ROLE_ID) if interaction.guild else None

        content, embed = order_update_embed(
            field="quantity",
            old_value=old_qty,
            new_value=new_quantity,
            worker_role=worker_role,
        )

        await interaction.channel.send(content=content, embed=embed)
        await safe_respond(interaction, content="✅ Order item quantity updated.", ephemeral=True)

    @app_commands.command(name="order-customer-update", description="(Staff) Change order customer")
    @app_commands.describe(customer="New customer (server member)")
    @app_commands.autocomplete(customer=user_autocomplete)
    async def update_customer(self, interaction: discord.Interaction, customer: str) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member):
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="order_update_customer", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        if not any(has_role(interaction.user, r) for r in ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Must be used in an order channel.", ephemeral=True)
            return

        if interaction.guild is None:
            await safe_respond(interaction, content="❌ Guild only.", ephemeral=True)
            return

        if not interaction.guild.get_member(int(customer)):
            await safe_respond(interaction, content="❌ Customer must be a server member.", ephemeral=True)
            return

        order = await self.order_serv.get_by_channel_id(str(interaction.channel.id))
        if not order:
            await safe_respond(interaction, content="❌ This is not an order channel.", ephemeral=True)
            return

        old_customer_id = order["customer_id"]

        try:
            updated = await self.order_serv.update_customer(order=order, new_customer_id=customer)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await update_order_embed(
            channel=interaction.channel,
            order=updated,
            worker_role_id=settings.WORKER_ROLE_ID,
        )

        worker_role = interaction.guild.get_role(settings.WORKER_ROLE_ID)
        content, embed = order_update_embed(
            field="customer",
            old_value=old_customer_id,
            new_value=customer,
            worker_role=worker_role,
        )

        await interaction.channel.send(content=content, embed=embed)
        await safe_respond(interaction, content="✅ Order customer updated.", ephemeral=True)

    @app_commands.command(name="force-claim", description="(Staff) Force claim to a worker")
    @app_commands.autocomplete(worker_id=worker_autocomplete)
    async def force_claim(self, interaction: discord.Interaction, worker_id: str, quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member):
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="force_claim", seconds=5)
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

        if order["customer_id"] == worker_id:
            await safe_respond(interaction, content="❌ Worker cannot claim his/her own order.", ephemeral=True)
            return

        try:
            updated = await self.order_claim_serv.force_claim(
                order_id=order["order_id"],
                worker_id=worker_id,
                qty=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await sync_order_category(channel=interaction.channel, order=updated)

        await update_order_embed(
            channel=interaction.channel,
            order=updated,
            worker_role_id=settings.WORKER_ROLE_ID,
        )

        guild = interaction.guild
        if guild:
            log_channel = guild.get_channel(settings.CLAIM_MESSAGE_CHANNEL_ID)
            worker = guild.get_member(int(worker_id))
            emoji = await self._get_item_emoji(order["item_id"])

            if isinstance(log_channel, discord.TextChannel) and worker:
                await log_channel.send(
                    embed=claim_log_embed(
                        worker=worker,
                        item_name=order["item_name"],
                        item_emoji=emoji,
                        quantity=quantity,
                        channel=interaction.channel,
                        action="force_claim",
                        staff=interaction.user,
                    )
                )

        await safe_respond(interaction, content="⚠️ Force claim executed.", ephemeral=True)

    @app_commands.command(name="force-unclaim", description="(Staff) Force unclaim to a worker")
    @app_commands.autocomplete(worker_id=claimed_worker_autocomplete)
    async def force_unclaim(self, interaction: discord.Interaction, worker_id: str, quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member):
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="force_unclaim", seconds=5)
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

        try:
            updated = await self.order_claim_serv.force_unclaim(
                order_id=order["order_id"],
                worker_id=worker_id,
                qty=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await sync_order_category(channel=interaction.channel, order=updated)

        await update_order_embed(
            channel=interaction.channel,
            order=updated,
            worker_role_id=settings.WORKER_ROLE_ID,
        )

        guild = interaction.guild
        if guild:
            log_channel = guild.get_channel(settings.CLAIM_MESSAGE_CHANNEL_ID)
            worker = guild.get_member(int(worker_id))
            emoji = await self._get_item_emoji(order["item_id"])

            if isinstance(log_channel, discord.TextChannel) and worker:
                await log_channel.send(
                    embed=claim_log_embed(
                        worker=worker,
                        item_name=order["item_name"],
                        item_emoji=emoji,
                        quantity=quantity,
                        channel=interaction.channel,
                        action="force_unclaim",
                        staff=interaction.user,
                    )
                )

        await safe_respond(interaction, content="⚠️ Force unclaim executed.", ephemeral=True)

    async def handle_close_order_button(self, interaction: discord.Interaction) -> None:
        await self.close_handler.handle_close_order_button(interaction)

    async def finalize_close_order(
        self,
        interaction: discord.Interaction,
        *,
        channel: discord.TextChannel,
    ) -> None:
        await self.close_handler.finalize_close_order(interaction, channel=channel)

    @commands.command(name="cancel")
    async def cancel_order(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member):
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="cancel_order", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            return

        if not any(has_role(ctx.author, r) for r in ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Staff only.", delete_after=5)
            return

        if not isinstance(ctx.channel, discord.TextChannel):
            return

        order = await self.order_serv.get_by_channel_id(str(ctx.channel.id))
        if not order:
            await ctx.send("❌ This is not an order channel.", delete_after=5)
            return

        if not await self._confirm(ctx, question="Are you sure you want to **CANCEL** this order?"):
            return

        try:
            await self.order_serv.cancel_order(order=order)
        except ValueError as exc:
            await ctx.send(f"❌ {exc}", delete_after=5)
            return

        await ctx.send("❌ Order canceled. Channel will be deleted.")
        await asyncio.sleep(5)
        await ctx.channel.delete(reason="Order canceled")

    async def calculate_worker_payment(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if not isinstance(interaction.user, discord.Member):
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="calc_worker_payment", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        if not any(has_role(interaction.user, r) for r in ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await safe_respond(interaction, content="❌ Guild only.", ephemeral=True)
            return

        view = CalcWorkerPaymentView(
            order_serv=self.order_serv,
            source_message=message,
            guild=guild,
            claimed_category_id=settings.CLAIMED_ORDERS_CATEGORY_ID,
            item_serv=self.item_serv,
        )

        await view.order_select.load()

        await safe_respond(
            interaction,
            content="🧮 **Calculate Worker Payment**",
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrderManagement(bot))