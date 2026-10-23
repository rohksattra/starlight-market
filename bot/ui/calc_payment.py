"""Ephemeral UI for Calculate Worker Payment context menu."""
from __future__ import annotations

from typing import Optional

import discord

from core.tenant import GameContext
from services import market_settings
from services.items import ItemService
from services.orders import OrderService
from utils.discord_safe import safe_defer, safe_edit_message, safe_respond

PAGE_SIZE = 20


class OrderSelect(discord.ui.Select):
    def __init__(self, view: "CalcWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(
            placeholder="Select worker first",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="Select a worker first", value="__none__")],
            custom_id="calc:select:order",
            disabled=True,
        )

    async def load(self) -> None:
        view = self.view_ref
        if view.worker_id is None:
            self.options = [discord.SelectOption(label="Select a worker first", value="__none__")]
            self.disabled = True
            self.max_values = 1
            self.placeholder = "Select worker first"
            view.prev_button.disabled = True
            view.next_button.disabled = True
            view.page_channel_ids = []
            return

        category = view.guild.get_channel(view.claimed_category_id)
        if not isinstance(category, discord.CategoryChannel):
            self.options = [discord.SelectOption(label="No claimed orders", value="__none__")]
            self.disabled = True
            self.max_values = 1
            view.page_channel_ids = []
            return

        worker_channels = []
        for ch, order in view.all_orders:
            claims = order.get("worker_claims") or {}
            if int(claims.get(view.worker_id, 0) or 0) > 0:
                worker_channels.append(ch)
        worker_channels.sort(key=lambda ch: str(ch.name).casefold())

        start = view.page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_channels = worker_channels[start:end]
        view.page_channel_ids = [str(ch.id) for ch in page_channels]

        self.options.clear()
        for ch in page_channels:
            self.options.append(
                discord.SelectOption(
                    label=f"#{ch.name}",
                    value=str(ch.id),
                    default=str(ch.id) == str(view.selected_order_id),
                )
            )

        if not self.options:
            self.options.append(discord.SelectOption(label="No claimed orders", value="__none__"))
            self.disabled = True
            self.max_values = 1
        else:
            self.disabled = False

        self.max_values = 1
        total_pages = max(1, (len(worker_channels) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.placeholder = f"Select Order (Page {view.page + 1}/{total_pages})"
        view.prev_button.disabled = view.page <= 0
        view.next_button.disabled = view.page >= (total_pages - 1)

    async def callback(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        if self.values and self.values[0] not in {"__none__"}:
            view = self.view_ref
            view.selected_order_id = self.values[0]
            view.order = None
            for ch, order in view.all_orders:
                if str(ch.id) == str(self.values[0]):
                    view.order = order
                    break
            view.quantity = None
            if view.order:
                self.placeholder = f"Order: #{view.order.get('order_number')} {view.order.get('item_name', 'Item')}"
        await self.view_ref.refresh_submit_state()
        await safe_edit_message(interaction, view=self.view_ref)


class WorkerSelect(discord.ui.Select):
    def __init__(self, view: "CalcWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(
            placeholder="Select Worker",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="Loading workers...", value="__placeholder__")],
            disabled=True,
            custom_id="calc:select:worker",
        )

    async def load(self, orders: list[dict] | None = None) -> None:
        worker_ids: set[str] = set()
        source = orders if orders is not None else [order for _ch, order in self.view_ref.all_orders]
        for order in source:
            for wid, qty in (order.get("worker_claims") or {}).items():
                if int(qty or 0) > 0:
                    worker_ids.add(str(wid))

        self.options.clear()
        members: list[tuple[str, discord.Member]] = []
        for wid in worker_ids:
            member = self.view_ref.guild.get_member(int(wid))
            if member:
                members.append((wid, member))
        members.sort(key=lambda item: str(item[1].display_name).casefold())

        for wid, member in members:
            self.options.append(
                discord.SelectOption(
                    label=member.display_name,
                    value=str(wid),
                    default=str(wid) == str(self.view_ref.worker_id),
                )
            )

        if not self.options:
            self.options.append(discord.SelectOption(label="No workers with claims", value="__placeholder__"))
            self.disabled = True
            return

        self.disabled = False
        if self.view_ref.worker_id is not None and str(self.view_ref.worker_id) not in worker_ids:
            self.view_ref.worker_id = None
            self.view_ref.selected_order_id = None
            self.view_ref.order = None

    async def callback(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        if self.values and self.values[0] not in {"__placeholder__", "__none__"}:
            self.view_ref.worker_id = self.values[0]
            self.view_ref.selected_order_id = None
            self.view_ref.order = None
            self.view_ref.quantity = None
            self.view_ref.page = 0
            member = self.view_ref.guild.get_member(int(self.values[0]))
            if member:
                self.placeholder = f"Worker: {member.display_name}"
        await self.view_ref.order_select.load()
        await self.view_ref.refresh_submit_state()
        await safe_edit_message(interaction, view=self.view_ref)


class QuantityModal(discord.ui.Modal, title="Set Quantity"):
    quantity = discord.ui.TextInput(label="Quantity", required=True, custom_id="quantity")

    def __init__(self, view: "CalcWorkerPaymentView") -> None:
        super().__init__(custom_id="calc:qty")
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.view_ref.selected_order_id is None:
            await safe_respond(interaction, content="❌ Select an order first.", ephemeral=True)
            return
        try:
            qty = int(self.quantity.value)
        except ValueError:
            await safe_respond(interaction, content="❌ Quantity must be a number.", ephemeral=True)
            return
        if qty < 0:
            await safe_respond(interaction, content="❌ Quantity cannot be negative.", ephemeral=True)
            return

        self.view_ref.quantity = qty
        await self.view_ref.refresh_submit_state()
        await safe_edit_message(
            interaction,
            content=f"🧮 Quantity set: **{qty}**",
            view=self.view_ref,
        )


class QuantityButton(discord.ui.Button):
    def __init__(self, view: "CalcWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(
            label="Set Quantity",
            style=discord.ButtonStyle.secondary,
            custom_id="calc:qty:open",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view_ref.selected_order_id is None:
            await safe_respond(interaction, content="❌ Select an order first.", ephemeral=True)
            return
        await interaction.response.send_modal(QuantityModal(self.view_ref))


class SubmitButton(discord.ui.Button):
    def __init__(self, view: "CalcWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(
            label="Calculate",
            style=discord.ButtonStyle.success,
            disabled=True,
            custom_id="calc:submit",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        await self.view_ref.handle_submit(interaction)


class PrevPageButton(discord.ui.Button):
    def __init__(self, view: "CalcWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(label="◀", style=discord.ButtonStyle.secondary, custom_id="calc:page:prev")

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.disabled or self.view_ref.page <= 0:
            return
        self.view_ref.page -= 1
        await self.view_ref.order_select.load()
        await safe_edit_message(interaction, view=self.view_ref)


class NextPageButton(discord.ui.Button):
    def __init__(self, view: "CalcWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(label="▶", style=discord.ButtonStyle.secondary, custom_id="calc:page:next")

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.disabled:
            return
        self.view_ref.page += 1
        await self.view_ref.order_select.load()
        await safe_edit_message(interaction, view=self.view_ref)


class CalcWorkerPaymentView(discord.ui.View):
    def __init__(
        self,
        *,
        ctx: GameContext,
        order_serv: OrderService,
        item_serv: ItemService,
        source_message: discord.Message,
        guild: discord.Guild,
        claimed_category_id: int,
    ) -> None:
        super().__init__(timeout=300)
        self.ctx = ctx
        self.order_serv = order_serv
        self.item_serv = item_serv
        self.source_message = source_message
        self.guild = guild
        self.claimed_category_id = claimed_category_id

        self.order: Optional[dict] = None
        self.selected_order_id: Optional[str] = None
        self.worker_id: Optional[str] = None
        self.quantity: Optional[int] = None
        self.page: int = 0
        self.page_channel_ids: list[str] = []
        self.all_orders: list[tuple[discord.TextChannel, dict]] = []

        self.worker_select = WorkerSelect(self)
        self.order_select = OrderSelect(self)
        self.prev_button = PrevPageButton(self)
        self.next_button = NextPageButton(self)
        self.qty_button = QuantityButton(self)
        self.submit_button = SubmitButton(self)

        self.add_item(self.worker_select)
        self.add_item(self.order_select)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.add_item(self.qty_button)
        self.add_item(self.submit_button)

    async def refresh_orders(self) -> None:
        category = self.guild.get_channel(self.claimed_category_id)
        self.all_orders = []
        if not isinstance(category, discord.CategoryChannel):
            await self.worker_select.load([])
            await self.order_select.load()
            return
        for ch in sorted(category.text_channels, key=lambda c: str(c.name).casefold()):
            order = await self.order_serv.get_by_channel_id(str(ch.id))
            if order:
                self.all_orders.append((ch, order))
        await self.worker_select.load([order for _ch, order in self.all_orders])
        await self.order_select.load()

    async def refresh_submit_state(self) -> None:
        self.submit_button.disabled = not (
            self.worker_id is not None
            and self.selected_order_id is not None
            and self.quantity is not None
        )

    async def handle_submit(self, interaction: discord.Interaction) -> None:
        if self.order is None or self.selected_order_id is None:
            await safe_respond(interaction, content="❌ Order not selected.", ephemeral=True)
            return
        fresh = await self.order_serv.get_by_channel_id(self.selected_order_id)
        if not fresh:
            await safe_respond(interaction, content="❌ Order no longer exists.", ephemeral=True)
            return
        self.order = fresh
        if self.worker_id is None:
            await safe_respond(interaction, content="❌ Worker not selected.", ephemeral=True)
            return
        if self.quantity is None:
            await safe_respond(interaction, content="❌ Quantity not set.", ephemeral=True)
            return
        worker_id = self.worker_id
        claimed_qty = int((fresh.get("worker_claims") or {}).get(worker_id, 0))
        if self.quantity > claimed_qty:
            await safe_respond(
                interaction,
                content=f"❌ Worker only claimed **{claimed_qty}** items.",
                ephemeral=True,
            )
            return
        keep_rate = await market_settings.keep_rate(self.ctx)
        item_price = int(fresh.get("item_price", 0) or 0)
        payment = int(item_price * self.quantity * keep_rate)
        item_id = fresh.get("item_id")
        item_emoji = await self.item_serv.get_item_emoji(item_id) if item_id else "🌟"
        item_emoji = item_emoji or "🌟"
        worker = self.guild.get_member(int(worker_id))
        worker_label = worker.mention if worker else f"<@{worker_id}>"
        content = (
            f"Calculate Worker Payment — {worker_label}\n\n"
            f"🏷 ***{self.quantity:,}x {item_emoji} {fresh.get('item_name', 'Item')}*** "
            f"(order # {fresh.get('order_number')}) for 🪙 ***{payment:,}***"
        )
        await safe_respond(interaction, content="✅ Payment calculated.", ephemeral=True)
        await self.source_message.reply(
            content,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.stop()
