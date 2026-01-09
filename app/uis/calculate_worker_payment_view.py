# app/uis/calculate_worker_payment_view.py
from __future__ import annotations

from typing import Optional, List

import discord

from core.config import WORKER_FEE_RATE
from app.services.order_service import OrderService
from utils.interaction_safe import (
    safe_defer,
    safe_respond,
    safe_edit_message,
)


PAGE_SIZE = 20


class OrderSelect(discord.ui.Select):
    def __init__(self, view: "CalcWorkerPaymentView"):
        self.view_ref = view
        super().__init__(placeholder="Select Order Channel", min_values=1, max_values=1, options=[])

    async def load(self) -> None:
        guild = self.view_ref.guild
        if guild is None:
            return
        category = guild.get_channel(self.view_ref.claimed_category_id)
        if not isinstance(category, discord.CategoryChannel):
            return
        channels = category.text_channels
        start = self.view_ref.page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_channels = channels[start:end]
        self.options.clear()
        for ch in page_channels:
            self.options.append(discord.SelectOption(label=f"#{ch.name}", value=str(ch.id)))
        if not self.options:
            self.options.append(discord.SelectOption(label="No claimed orders", value="__none__"))
            self.disabled = True
        else:
            self.disabled = False
        total_pages = max(1, (len(channels) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.placeholder = f"Select Order (Page {self.view_ref.page + 1}/{total_pages})"
        self.view_ref.prev_button.disabled = self.view_ref.page <= 0
        self.view_ref.next_button.disabled = self.view_ref.page >= (total_pages - 1)

    async def callback(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        guild = self.view_ref.guild
        if guild is None:
            return
        channel_id = self.values[0]
        if channel_id == "__none__":
            return
        order = await self.view_ref.order_serv.get_by_channel_id(channel_id)
        if not order:
            await safe_respond(interaction, content="❌ Order not found.", ephemeral=True)
            return
        self.view_ref.order = order
        self.view_ref.quantity = None
        self.view_ref.submit_button.disabled = True
        self.view_ref.worker_select.disabled = False
        channel = guild.get_channel(int(channel_id))
        if isinstance(channel, discord.TextChannel):
            self.placeholder = f"Order: #{channel.name}"
        await self.view_ref.worker_select.load(order)
        await safe_edit_message(interaction, view=self.view_ref)


class WorkerSelect(discord.ui.Select):
    def __init__(self, view: "CalcWorkerPaymentView"):
        self.view_ref = view
        super().__init__(
            placeholder="Select Worker",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="Select order first", value="__placeholder__")],
            disabled=True,
        )

    async def load(self, order: dict) -> None:
        guild = self.view_ref.guild
        if guild is None:
            return
        self.options.clear()
        for worker_id, qty in order.get("worker_claims", {}).items():
            if qty <= 0:
                continue
            member = guild.get_member(int(worker_id))
            if not member:
                continue
            self.options.append(discord.SelectOption(label=member.display_name, value=str(worker_id), description=f"Claimed {qty}"))
        if not self.options:
            self.options.append(discord.SelectOption(label="No workers found", value="__none__"))
            self.disabled = True
        else:
            self.disabled = False

    async def callback(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        if self.values[0] == "__none__":
            return
        guild = self.view_ref.guild
        if guild is None:
            return
        member = guild.get_member(int(self.values[0]))
        if member:
            self.placeholder = f"Worker: {member.display_name}"
        self.view_ref.submit_button.disabled = self.view_ref.quantity is None
        await safe_edit_message(interaction, view=self.view_ref)


class QuantityModal(discord.ui.Modal, title="Set Quantity"):
    quantity = discord.ui.TextInput(label="Quantity", required=True)
    def __init__(self, view: "CalcWorkerPaymentView"):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            qty = int(self.quantity.value)
        except ValueError:
            await safe_respond(interaction, content="❌ Quantity must be a number.", ephemeral=True)
            return
        if qty <= 0:
            await safe_respond(interaction, content="❌ Quantity must be greater than 0.", ephemeral=True)
            return
        self.view_ref.quantity = qty
        self.view_ref.submit_button.disabled = False
        await safe_edit_message(interaction, content=f"🧮 Quantity set: **{qty}**", view=self.view_ref)


class QuantityButton(discord.ui.Button):
    def __init__(self, view: "CalcWorkerPaymentView"):
        self.view_ref = view
        super().__init__(label="Set Quantity", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(QuantityModal(self.view_ref))


class SubmitButton(discord.ui.Button):
    def __init__(self, view: "CalcWorkerPaymentView"):
        self.view_ref = view
        super().__init__(label="Calculate", style=discord.ButtonStyle.success, disabled=True)

    async def callback(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        await self.view_ref.handle_submit(interaction)


class PrevPageButton(discord.ui.Button):
    def __init__(self, view: "CalcWorkerPaymentView"):
        self.view_ref = view
        super().__init__(label="◀", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.disabled:
            return
        if self.view_ref.page <= 0:
            return
        self.view_ref.page -= 1
        await self.view_ref.order_select.load()
        await safe_edit_message(interaction, view=self.view_ref)


class NextPageButton(discord.ui.Button):
    def __init__(self, view: "CalcWorkerPaymentView"):
        self.view_ref = view
        super().__init__(label="▶", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.disabled:
            return
        self.view_ref.page += 1
        await self.view_ref.order_select.load()
        await safe_edit_message(interaction, view=self.view_ref)


class CalcWorkerPaymentView(discord.ui.View):
    def __init__(self, *, order_serv: OrderService, source_message: discord.Message, guild: discord.Guild, claimed_category_id: int):
        super().__init__(timeout=300)
        self.order_serv = order_serv
        self.source_message = source_message
        self.guild = guild
        self.claimed_category_id = claimed_category_id
        self.order: Optional[dict] = None
        self.quantity: Optional[int] = None
        self.page: int = 0
        self.order_select = OrderSelect(self)
        self.worker_select = WorkerSelect(self)
        self.prev_button = PrevPageButton(self)
        self.next_button = NextPageButton(self)
        self.qty_button = QuantityButton(self)
        self.submit_button = SubmitButton(self)
        self.add_item(self.order_select)
        self.add_item(self.worker_select)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.add_item(self.qty_button)
        self.add_item(self.submit_button)

    async def handle_submit(self, interaction: discord.Interaction) -> None:
        if not self.order:
            await safe_respond(interaction, content="❌ Order not selected.", ephemeral=True)
            return
        fresh = await self.order_serv.get_by_channel_id(self.order["channel_id"])
        if not fresh:
            await safe_respond(interaction, content="❌ Order no longer exists.", ephemeral=True)
            return
        self.order = fresh
        if not self.worker_select.values:
            await safe_respond(interaction, content="❌ Worker not selected.", ephemeral=True)
            return
        if self.quantity is None:
            await safe_respond(interaction, content="❌ Quantity not set.", ephemeral=True)
            return
        worker_id = self.worker_select.values[0]
        claimed_qty = int(self.order["worker_claims"].get(worker_id, 0))
        if self.quantity > claimed_qty:
            await safe_respond(interaction, content=f"❌ Worker only claimed **{claimed_qty}** items.", ephemeral=True)
            return
        item_price = int(self.order["item_price"])
        payment = int(item_price * self.quantity * WORKER_FEE_RATE)
        await safe_respond(interaction, content="✅ Payment calculated.", ephemeral=True)
        await self.source_message.reply(
            (
                f"🏷 ***{self.quantity:,}x {self.order['item_name']}*** "
                f"for 🪙 ***{payment:,}***"
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.stop()
