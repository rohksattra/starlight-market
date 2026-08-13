"""Slash and prefix commands for orders."""
from __future__ import annotations

from typing import Dict, List, Literal, cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.handlers.orders import get_order_handler
from bot.ui.orders import OrderEntryView, order_entry_embed
from core.tenant import get_context
from models.enums import ORDER_MANAGEMENT_ROLES, OrderStatus
from services.orders import OrderService
from utils.autocomplete import fallback_user_label, user_autocomplete
from utils.cooldown import check_cooldown
from utils.discord_safe import safe_defer, safe_respond
from utils.permissions import has_any_role
from utils.prefix_feedback import failed, success

IncomeTarget = Literal["worker", "customer"]


class OrderCommands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.handler = get_order_handler()
        self.bot.add_view(OrderEntryView(self.start_order))

        self.calc_worker_ctx = app_commands.ContextMenu(
            name="Calculate Worker Payment",
            callback=self.calculate_worker_payment,
        )
        old = self.bot.tree.get_command(
            "Calculate Worker Payment",
            type=discord.AppCommandType.message,
        )
        if old is not None:
            self.bot.tree.remove_command(
                "Calculate Worker Payment",
                type=discord.AppCommandType.message,
            )
        self.bot.tree.add_command(self.calc_worker_ctx)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.calc_worker_ctx.name,
            type=self.calc_worker_ctx.type,
        )

    async def start_order(self, interaction: discord.Interaction) -> None:
        await self.handler.start_order_flow(interaction)

    @commands.command(name="morder")
    async def order_entry_panel(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.guild is None:
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            await failed(ctx)
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="order_panel", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return

        if not has_any_role(ctx.author, tenant, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Staff only.", delete_after=5)
            await failed(ctx)
            return

        channel = ctx.guild.get_channel(tenant.channels.place_order)
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Place order channel not found.", delete_after=5)
            await failed(ctx)
            return

        role = ctx.guild.get_role(tenant.roles.bank_manager)
        role_mention = role.mention if role else "@Bank Manager"

        await channel.send(
            embed=order_entry_embed(role_mention, tenant),
            view=OrderEntryView(self.start_order),
        )
        await success(ctx)

    @app_commands.command(name="claim", description="(Worker) Claim items from this order")
    async def claim(self, interaction: discord.Interaction, quantity: int) -> None:
        try:
            check_cooldown(user_id=interaction.user.id, key="claim", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        await self.handler.handle_claim_action(interaction, action="claim", quantity=quantity)

    @app_commands.command(name="unclaim", description="(Worker) Cancel your claim")
    async def unclaim(self, interaction: discord.Interaction, quantity: int) -> None:
        try:
            check_cooldown(user_id=interaction.user.id, key="unclaim", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        await self.handler.handle_claim_action(interaction, action="unclaim", quantity=quantity)

    async def income_user_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            return []

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            return []

        order = await OrderService(ctx).get_by_channel_id(str(interaction.channel.id))
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
                label = (
                    f"{member.display_name} ({member.name})"
                    if member
                    else fallback_user_label(wid)
                )
                if current_lower and current_lower not in label.lower() and current_lower not in wid:
                    continue
                results.append(app_commands.Choice(name=label[:100], value=str(wid)))

        elif target == "customer":
            cid = order.get("customer_id")
            if cid:
                member = interaction.guild.get_member(int(cid))
                label = (
                    f"{member.display_name} ({member.name})"
                    if member
                    else fallback_user_label(str(cid))
                )
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
    @app_commands.autocomplete(user=income_user_autocomplete)
    async def income(
        self,
        interaction: discord.Interaction,
        target: IncomeTarget,
        user: str,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not await self._require_staff_interaction(interaction, key="income"):
            return
        await self.handler.handle_record_income(
            interaction,
            target=target,
            user=user,
            quantity=quantity,
        )

    @app_commands.command(name="custom-order", description="(Staff) Create a custom/manual order for a member")
    @app_commands.describe(
        customer="Customer (server member)",
        item_name="Custom item name",
        item_price="Price per item",
        quantity="Item quantity",
    )
    @app_commands.autocomplete(customer=user_autocomplete)
    async def custom_order(
        self,
        interaction: discord.Interaction,
        customer: str,
        item_name: str,
        item_price: int,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not await self._require_staff_interaction(interaction, key="custom_order"):
            return
        await self.handler.handle_custom_order(
            interaction,
            customer=customer,
            item_name=item_name,
            item_price=item_price,
            quantity=quantity,
        )

    @app_commands.command(name="order-item-price-update", description="(Staff) Update order item price")
    async def update_price(self, interaction: discord.Interaction, new_price: int) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not await self._require_staff_interaction(interaction, key="order_update_price"):
            return
        await self.handler.handle_update_price(interaction, new_price=new_price)

    @app_commands.command(name="order-item-quantity-update", description="(Staff) Update order item quantity")
    async def update_quantity(self, interaction: discord.Interaction, new_quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not await self._require_staff_interaction(interaction, key="order_update_quantity"):
            return
        await self.handler.handle_update_quantity(interaction, new_quantity=new_quantity)

    @app_commands.command(name="order-customer-update", description="(Staff) Change order customer")
    @app_commands.describe(customer="New customer (server member)")
    @app_commands.autocomplete(customer=user_autocomplete)
    async def update_customer(self, interaction: discord.Interaction, customer: str) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not await self._require_staff_interaction(interaction, key="order_update_customer"):
            return
        await self.handler.handle_update_customer(interaction, customer=customer)

    async def worker_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            return []

        worker_role = interaction.guild.get_role(ctx.roles.worker)
        if worker_role is None:
            return []

        current_lower = current.lower()
        choices: List[app_commands.Choice[str]] = []
        for member in sorted(worker_role.members, key=lambda m: m.display_name.lower()):
            if member.bot:
                continue
            if (
                current_lower
                and current_lower not in member.display_name.lower()
                and current_lower not in member.name.lower()
            ):
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

    async def claimed_worker_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if not isinstance(interaction.channel, discord.TextChannel) or interaction.guild is None:
            return []

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            return []

        order = await OrderService(ctx).get_by_channel_id(str(interaction.channel.id))
        if not order:
            return []

        current_lower = current.lower()
        choices: List[app_commands.Choice[str]] = []
        for wid, qty in sorted(order.get("worker_claims", {}).items(), key=lambda item: item[0]):
            if qty <= 0:
                continue
            member = interaction.guild.get_member(int(wid))
            label = (
                f"{member.display_name} ({member.name}) — qty {qty}"
                if member
                else f"{fallback_user_label(wid)} — qty {qty}"
            )
            if current_lower and current_lower not in label.lower() and current_lower not in wid:
                continue
            choices.append(app_commands.Choice(name=label[:100], value=str(wid)))
            if len(choices) >= 25:
                break
        return choices

    @app_commands.command(name="force-claim", description="(Staff) Force claim to a worker")
    @app_commands.autocomplete(worker_id=worker_autocomplete)
    async def force_claim(
        self,
        interaction: discord.Interaction,
        worker_id: str,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not await self._require_staff_interaction(interaction, key="force_claim"):
            return
        await self.handler.handle_force_claim(interaction, worker_id=worker_id, quantity=quantity)

    @app_commands.command(name="force-unclaim", description="(Staff) Force unclaim to a worker")
    @app_commands.autocomplete(worker_id=claimed_worker_autocomplete)
    async def force_unclaim(
        self,
        interaction: discord.Interaction,
        worker_id: str,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not await self._require_staff_interaction(interaction, key="force_unclaim"):
            return
        await self.handler.handle_force_unclaim(interaction, worker_id=worker_id, quantity=quantity)

    @commands.command(name="mcancel")
    async def cancel_order(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or ctx.guild is None:
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="cancel_order", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            await failed(ctx)
            return

        if not has_any_role(ctx.author, tenant, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Staff only.", delete_after=5)
            await failed(ctx)
            return

        await self.handler.handle_cancel_order(ctx)

    async def calculate_worker_payment(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not await self._require_staff_interaction(interaction, key="calc_worker_payment"):
            return
        await self.handler.handle_calculate_worker_payment(interaction, message)

    async def _require_staff_interaction(self, interaction: discord.Interaction, *, key: str) -> bool:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            return False
        try:
            check_cooldown(user_id=interaction.user.id, key=key, seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return False
        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return False
        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return False
        return True


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrderCommands(bot))
