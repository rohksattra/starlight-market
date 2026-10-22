"""Ephemeral UI for Calculate Worker Payment (Multi) context menu."""
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
    def __init__(self, view: "CalcMultiWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(
            placeholder="Select worker first",
            min_values=0,
            max_values=1,
            options=[discord.SelectOption(label="Select a worker first", value="__none__")],
            custom_id="calc:multi:select:order",
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

        guild = view.guild
        category = guild.get_channel(view.claimed_category_id)
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

        # Use worker_channels (already filtered) for pagination.
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
                    default=str(ch.id) in view.selected,
                )
            )

        if not self.options:
            self.options.append(discord.SelectOption(label="No claimed orders", value="__none__"))
            self.disabled = True
            self.max_values = 1
        else:
            self.disabled = False

        self.max_values = max(1, min(PAGE_SIZE, len(page_channels) or 1))

        total_pages = max(1, (len(worker_channels) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.placeholder = f"Select Orders (Page {view.page + 1}/{total_pages})"
        view.prev_button.disabled = view.page <= 0
        view.next_button.disabled = view.page >= (total_pages - 1)


    async def callback(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        if self.values and self.values[0] == "__none__":
            return
        await self.view_ref.sync_selection(self.view_ref.page_channel_ids, self.values)
        await self.view_ref.qty_order_select.load()
        await self.view_ref.refresh_submit_state()
        await safe_edit_message(interaction, view=self.view_ref)


class WorkerSelect(discord.ui.Select):
    def __init__(self, view: "CalcMultiWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(
            placeholder="Select Worker",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="Loading workers...", value="__placeholder__")],
            disabled=True,
            custom_id="calc:multi:select:worker",
        )

    async def load(self) -> None:
        worker_ids: set[str] = set()
        for _ch, order in self.view_ref.all_orders:
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

    async def callback(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        if self.values and self.values[0] not in {"__placeholder__", "__none__"}:
            self.view_ref.worker_id = self.values[0]
            # Reset selected orders when worker changes.
            self.view_ref.selected.clear()
            self.view_ref.qty_target = None
            self.view_ref.page = 0
            member = self.view_ref.guild.get_member(int(self.values[0]))
            if member:
                self.placeholder = f"Worker: {member.display_name}"
        await self.view_ref.order_select.load()
        await self.view_ref.qty_order_select.load()
        await self.view_ref.refresh_submit_state()
        await safe_edit_message(interaction, view=self.view_ref)


class QtyOrderSelect(discord.ui.Select):
    def __init__(self, view: "CalcMultiWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(
            placeholder="Select order to set quantity",
            min_values=0,
            max_values=1,
            options=[discord.SelectOption(label="No selected orders", value="__none__")],
            disabled=True,
            custom_id="calc:multi:select:qty_order",
        )

    async def load(self) -> None:
        view = self.view_ref
        self.options.clear()
        if not view.selected:
            self.options.append(discord.SelectOption(label="No selected orders", value="__none__"))
            self.disabled = True
            return
        for channel_id, info in view.selected.items():
            order = info.get("order") or {}
            qty = int(info.get("qty", 0) or 0)
            label = f"#{order.get('order_number')} {order.get('item_name', 'Item')} (qty {qty})"
            self.options.append(discord.SelectOption(label=label[:100], value=str(channel_id)))
        self.disabled = False

    async def callback(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        if self.values and self.values[0] not in {"__none__"}:
            self.view_ref.qty_target = self.values[0]
        await safe_edit_message(interaction, view=self.view_ref)


class QuantityModal(discord.ui.Modal, title="Set Quantity"):
    quantity = discord.ui.TextInput(label="Quantity", required=True, custom_id="quantity")

    def __init__(self, view: "CalcMultiWorkerPaymentView") -> None:
        super().__init__(custom_id="calc:multi:qty")
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        target = self.view_ref.qty_target
        if target is None or target not in self.view_ref.selected:
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

        self.view_ref.selected[target]["qty"] = qty
        await self.view_ref.qty_order_select.load()
        await safe_edit_message(
            interaction,
            content=f"🧮 Quantity set: **{qty}**",
            view=self.view_ref,
        )


class QuantityButton(discord.ui.Button):
    def __init__(self, view: "CalcMultiWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(
            label="Set Quantity",
            style=discord.ButtonStyle.secondary,
            custom_id="calc:multi:qty:open",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view_ref.qty_target is None:
            await safe_respond(interaction, content="❌ Select an order first.", ephemeral=True)
            return
        await interaction.response.send_modal(QuantityModal(self.view_ref))


class SubmitButton(discord.ui.Button):
    def __init__(self, view: "CalcMultiWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(
            label="Calculate",
            style=discord.ButtonStyle.success,
            disabled=True,
            custom_id="calc:multi:submit",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        await self.view_ref.handle_submit(interaction)


class PrevPageButton(discord.ui.Button):
    def __init__(self, view: "CalcMultiWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(label="◀", style=discord.ButtonStyle.secondary, custom_id="calc:multi:page:prev")

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.disabled or self.view_ref.page <= 0:
            return
        self.view_ref.page -= 1
        await self.view_ref.order_select.load()
        await safe_edit_message(interaction, view=self.view_ref)


class NextPageButton(discord.ui.Button):
    def __init__(self, view: "CalcMultiWorkerPaymentView") -> None:
        self.view_ref = view
        super().__init__(label="▶", style=discord.ButtonStyle.secondary, custom_id="calc:multi:page:next")

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.disabled:
            return
        self.view_ref.page += 1
        await self.view_ref.order_select.load()
        await safe_edit_message(interaction, view=self.view_ref)


class CalcMultiWorkerPaymentView(discord.ui.View):
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

        self.selected: dict[str, dict] = {}
        self.worker_id: Optional[str] = None
        self.qty_target: Optional[str] = None
        self.page: int = 0
        self.page_channel_ids: list[str] = []
        self.all_orders: list[tuple[discord.TextChannel, dict]] = []

        self.order_select = OrderSelect(self)
        self.worker_select = WorkerSelect(self)
        self.qty_order_select = QtyOrderSelect(self)
        self.prev_button = PrevPageButton(self)
        self.next_button = NextPageButton(self)
        self.qty_button = QuantityButton(self)
        self.submit_button = SubmitButton(self)

        self.add_item(self.worker_select)
        self.add_item(self.order_select)
        self.add_item(self.qty_order_select)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.add_item(self.qty_button)
        self.add_item(self.submit_button)

    async def refresh_category_orders(self) -> None:
        guild = self.guild
        category = guild.get_channel(self.claimed_category_id)
        self.all_orders = []
        if not isinstance(category, discord.CategoryChannel):
            return
        for ch in sorted(category.text_channels, key=lambda c: str(c.name).casefold()):
            order = await self.order_serv.get_by_channel_id(str(ch.id))
            if order:
                self.all_orders.append((ch, order))

    async def sync_selection(self, page_ids: list[str], selected_values: list[str]) -> None:
        selected_set = set(selected_values or [])
        # Remove orders deselected on the current page.
        for cid in page_ids:
            if cid not in selected_set and cid in self.selected:
                del self.selected[cid]

        # Add newly selected orders (default qty 0).
        for cid in selected_set:
            if cid in self.selected:
                continue
            if len(self.selected) >= 25:
                continue
            order = None
            for ch, o in self.all_orders:
                if str(ch.id) == str(cid):
                    order = o
                    break
            if order is None:
                order = await self.order_serv.get_by_channel_id(cid)
            if not order:
                continue
            self.selected[cid] = {"order": order, "qty": 0}

        if self.qty_target is not None and self.qty_target not in self.selected:
            self.qty_target = None
        await self.refresh_submit_state()

    async def refresh_submit_state(self) -> None:
        self.submit_button.disabled = not (self.worker_id and self.selected)

    async def handle_submit(self, interaction: discord.Interaction) -> None:
        if not self.selected:
            await safe_respond(interaction, content="❌ No orders selected.", ephemeral=True)
            return
        if self.worker_id is None:
            await safe_respond(interaction, content="❌ Worker not selected.", ephemeral=True)
            return

        keep_rate = await market_settings.keep_rate(self.ctx)

        lines: list[str] = []
        total = 0
        for channel_id, info in self.selected.items():
            fresh = await self.order_serv.get_by_channel_id(channel_id)
            if not fresh:
                await safe_respond(interaction, content="❌ One of the orders no longer exists.", ephemeral=True)
                return

            qty = int(info.get("qty", 0) or 0)
            if qty <= 0:
                continue

            claimed_qty = int((fresh.get("worker_claims") or {}).get(self.worker_id, 0))
            if qty > claimed_qty:
                await safe_respond(
                    interaction,
                    content=f"❌ Worker only claimed **{claimed_qty}** items for order #{fresh.get('order_number')}.",
                    ephemeral=True,
                )
                return

            item_price = int(fresh.get("item_price", 0) or 0)
            payment = int(item_price * qty * keep_rate)
            total += payment

            item_id = fresh.get("item_id")
            item_emoji = await self.item_serv.get_item_emoji(item_id) if item_id else "🌟"
            item_emoji = item_emoji or "🌟"
            lines.append(
                f"🏷 ***{qty:,}x {item_emoji} {fresh.get('item_name', 'Item')}*** "
                f"(order #{fresh.get('order_number')}) for 🪙 ***{payment:,}***"
            )

        if not lines:
            await safe_respond(interaction, content="❌ Set at least one quantity greater than 0.", ephemeral=True)
            return

        worker = self.guild.get_member(int(self.worker_id))
        worker_label = worker.mention if worker else f"<@{self.worker_id}>"

        content = (
            f"Calculate Worker Payment (Multi) — {worker_label}\n\n"
            + "\n".join(lines)
            + f"\n\nTotal: 🪙 ***{total:,}***"
        )

        await safe_respond(interaction, content="✅ Payment calculated.", ephemeral=True)
        await self.source_message.reply(
            content,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.stop()
