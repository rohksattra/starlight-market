# app/cogs/order_management.py
from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from core.config import settings
from core.role_map import has_role
from app.domains.enums.order_status_enum import OrderStatus
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.repositories.order_repo import OrderRepository
from app.services.order_claim_service import OrderClaimService
from app.services.order_service import OrderService
from app.uis.calculate_worker_payment_view import CalcWorkerPaymentView
from app.uis.claim_embed import claim_log_embed
from app.uis.order_embed import update_order_embed
from app.uis.order_update_embed import order_update_embed
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown


MAX_ACTIVE_CLAIM = 6


async def worker_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    guild = interaction.guild
    if guild is None:
        return []
    worker_role = guild.get_role(settings.WORKER_ROLE_ID)
    if worker_role is None:
        return []
    current_lower = current.lower()
    choices: list[app_commands.Choice[str]] = []
    for member in worker_role.members:
        if member.bot:
            continue
        if current_lower not in member.display_name.lower():
            continue
        choices.append(app_commands.Choice(name=f"{member.display_name} ({member.name})", value=str(member.id)))
        if len(choices) >= 25:
            break
    return choices


async def claimed_worker_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not isinstance(interaction.channel, discord.TextChannel):
        return []
    guild = interaction.guild
    if guild is None:
        return []
    repo = OrderRepository()
    order = await repo.get_by_channel_id(str(interaction.channel.id))
    if not order:
        return []
    current_lower = current.lower()
    choices: list[app_commands.Choice[str]] = []
    for wid, qty in order.get("worker_claims", {}).items():
        if qty <= 0:
            continue
        member = guild.get_member(int(wid))
        if not member:
            continue
        name = member.display_name
        if current_lower not in name.lower():
            continue
        choices.append(app_commands.Choice(name=f"{member.display_name} ({member.name})", value=str(wid)))
        if len(choices) >= 25:
            break
    return choices


class OrderManagement(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.order_serv = OrderService()
        self.order_claim_serv = OrderClaimService()
        self.calc_worker_ctx = app_commands.ContextMenu(name="Calculate Worker Payment", callback=self.calculate_worker_payment)
        self.bot.tree.add_command(self.calc_worker_ctx)

    async def _active_claim_count(self, worker_id: str) -> int:
        return await self.order_serv.count_active_by_worker(worker_id)

    async def _confirm(self, ctx: commands.Context, *, question: str) -> bool:
        await ctx.send(f"⚠️ **Confirmation Required**\n\n{question}\n\nReply with **Yes** or **No**.", delete_after=60)
        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel
        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Confirmation timed out.", delete_after=5)
            return False
        return msg.content.lower() in {"yes", "y"}
    
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
        await update_order_embed(channel=interaction.channel, order=updated, worker_role_id=settings.WORKER_ROLE_ID)
        worker_role = interaction.guild.get_role(settings.WORKER_ROLE_ID) if interaction.guild else None
        await interaction.channel.send(
            embed=order_update_embed( field="price", old_value=old_price, new_value=new_price, worker_role=worker_role)
        )
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
        await update_order_embed(channel=interaction.channel, order=updated, worker_role_id=settings.WORKER_ROLE_ID)
        safe_name = (f"{updated['item_quantity']}-{updated['item_name']}".lower().replace(" ", "-"))[:90]
        new_name = f"【{updated['order_number']}-📦】{safe_name}"
        if interaction.channel.name != new_name:
            await interaction.channel.edit(name=new_name)
        worker_role = interaction.guild.get_role(settings.WORKER_ROLE_ID) if interaction.guild else None
        await interaction.channel.send(
            embed=order_update_embed(field="quantity", old_value=old_qty, new_value=new_quantity, worker_role=worker_role)
        )
        await safe_respond(interaction, content="✅ Order item quantity updated.", ephemeral=True)

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
        already_claimed = order.get("worker_claims", {}).get(worker_id, 0) > 0
        if not already_claimed:
            active = await self._active_claim_count(worker_id)
            if active >= MAX_ACTIVE_CLAIM:
                await safe_respond(interaction, content=f"❌ Claim limit reached (**{active}/{MAX_ACTIVE_CLAIM}**).", ephemeral=True)
                return
        try:
            updated = await self.order_claim_serv.force_claim(order_id=order["order_id"], worker_id=worker_id, qty=quantity)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        await self._sync_category(channel=interaction.channel, order=updated)
        await update_order_embed(channel=interaction.channel, order=updated, worker_role_id=settings.WORKER_ROLE_ID)
        guild = interaction.guild
        if guild:
            log_channel = guild.get_channel(settings.CLAIM_MESSAGE_CHANNEL_ID)
            worker = guild.get_member(int(worker_id))
            if isinstance(log_channel, discord.TextChannel) and worker:
                await log_channel.send(
                    embed=claim_log_embed(
                        worker=worker,
                        item_name=order["item_name"],
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
            updated = await self.order_claim_serv.force_unclaim(order_id=order["order_id"], worker_id=worker_id, qty=quantity)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        await self._sync_category(channel=interaction.channel, order=updated)
        await update_order_embed(channel=interaction.channel, order=updated, worker_role_id=settings.WORKER_ROLE_ID)
        guild = interaction.guild
        if guild:
            log_channel = guild.get_channel(settings.CLAIM_MESSAGE_CHANNEL_ID)
            worker = guild.get_member(int(worker_id))
            if isinstance(log_channel, discord.TextChannel) and worker:
                await log_channel.send(
                    embed=claim_log_embed(
                        worker=worker, item_name=order["item_name"],
                        quantity=quantity,
                        channel=interaction.channel,
                        action="force_unclaim",
                        staff=interaction.user,
                    )
                )
        await safe_respond(interaction, content="⚠️ Force unclaim executed.", ephemeral=True)

    @commands.command(name="close")
    async def close_order(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member):
            return
        try:
            check_cooldown(user_id=ctx.author.id, key="close_order", seconds=5)
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
        if order["order_status"] != OrderStatus.DELIVERED:
            await ctx.send("❌ Only delivered orders can be closed.", delete_after=5)
            return
        if not await self._confirm(ctx, question="Are you sure you want to **FINALIZE** this order?"):
            return
        try:
            await self.order_serv.close_order(order=order)
        except ValueError as exc:
            await ctx.send(f"❌ {exc}", delete_after=5)
            return
        await ctx.send("✅ Order closed. Channel will be deleted.")
        await asyncio.sleep(5)
        await ctx.channel.delete(reason="Order closed")

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

    async def calculate_worker_payment(self, interaction: discord.Interaction, message: discord.Message) -> None:
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
            order_serv=self.order_serv, source_message=message, guild=guild, claimed_category_id=settings.CLAIMED_ORDERS_CATEGORY_ID,
        )
        await view.order_select.load()
        await safe_respond(interaction, content="🧮 **Calculate Worker Payment**", view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrderManagement(bot))
