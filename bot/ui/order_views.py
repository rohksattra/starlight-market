"""Order buttons and modals."""
from __future__ import annotations

import logging
from typing import Awaitable, Callable
from uuid import uuid4

import discord
from discord.errors import NotFound

from utils.discord_safe import safe_defer, safe_edit_message, safe_respond

log = logging.getLogger("bot.ui.orders")

class OrderEntryView(discord.ui.View):
    def __init__(self, on_start: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=None)
        self.on_start = on_start

    @discord.ui.button(label="🛒 Order Now", style=discord.ButtonStyle.primary, custom_id="order:entry:start")
    async def order_now(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        from utils.discord_safe import safe_defer

        await safe_defer(interaction, ephemeral=True)
        await self.on_start(interaction)


class OrderClaimView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.claim_btn = discord.ui.Button(
            label="Claim",
            style=discord.ButtonStyle.success,
            custom_id="orderclaim:claim",
        )
        self.unclaim_btn = discord.ui.Button(
            label="Unclaim",
            style=discord.ButtonStyle.danger,
            custom_id="orderclaim:unclaim",
        )
        self.refresh_btn = discord.ui.Button(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            custom_id="orderclaim:refresh",
        )
        self.claim_btn.callback = self.claim
        self.unclaim_btn.callback = self.unclaim
        self.refresh_btn.callback = self.refresh
        self.add_item(self.claim_btn)
        self.add_item(self.unclaim_btn)
        self.add_item(self.refresh_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    async def claim(self, interaction: discord.Interaction) -> None:
        from bot.handlers.orders import get_order_handler

        async def on_submit(inter2: discord.Interaction, qty: int) -> None:
            try:
                await get_order_handler().handle_claim_action(inter2, action="claim", quantity=qty)
            except Exception:
                log.exception("Failed to claim order")
                from utils.discord_safe import safe_respond

                await safe_respond(inter2, content="❌ Failed to claim.", ephemeral=True)

        await interaction.response.send_modal(QuantityModal(on_submit=on_submit, kind="claim"))

    async def unclaim(self, interaction: discord.Interaction) -> None:
        from bot.handlers.orders import get_order_handler

        async def on_submit(inter2: discord.Interaction, qty: int) -> None:
            try:
                await get_order_handler().handle_claim_action(inter2, action="unclaim", quantity=qty)
            except Exception:
                log.exception("Failed to unclaim order")
                from utils.discord_safe import safe_respond

                await safe_respond(inter2, content="❌ Failed to unclaim.", ephemeral=True)

        await interaction.response.send_modal(QuantityModal(on_submit=on_submit, kind="unclaim"))

    async def refresh(self, interaction: discord.Interaction) -> None:
        from bot.handlers.orders import get_order_handler
        from utils.discord_safe import safe_defer, safe_respond

        await safe_defer(interaction, ephemeral=True)
        try:
            await get_order_handler().handle_claim_refresh(interaction)
            await safe_respond(interaction, content="✅ Refreshed.", ephemeral=True)
        except Exception:
            log.exception("Failed to refresh order view")
            await safe_respond(interaction, content="❌ Failed to refresh.", ephemeral=True)


class QuantityModal(discord.ui.Modal, title="Quantity"):
    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="Enter number",
        required=True,
        custom_id="quantity",
    )

    def __init__(
        self,
        on_submit: Callable[[discord.Interaction, int], Awaitable[None]],
        *,
        kind: str = "place",
    ) -> None:
        super().__init__(custom_id=f"order:qty:{kind}")
        self._cb = on_submit

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from utils.discord_safe import safe_respond

        try:
            qty = int(self.quantity.value)
        except ValueError:
            await safe_respond(interaction, content="❌ Quantity must be a number.", ephemeral=True)
            return
        if qty <= 0:
            await safe_respond(interaction, content="❌ Quantity must be greater than 0.", ephemeral=True)
            return
        await self._cb(interaction, qty)


MORE = "__more__"
PREV = "__prev__"


class OrderCategoryView(discord.ui.View):
    def __init__(
        self,
        *,
        user_id: int,
        categories: list[str],
        page: int,
        page_size: int,
        on_select: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.categories = categories
        self.page = page
        self.page_size = page_size
        self.on_select = on_select
        self.select = discord.ui.Select(
            placeholder="Select category",
            min_values=1,
            max_values=1,
            custom_id="order:select:category",
        )
        self.select.callback = self._handle
        self.add_item(self.select)
        self._render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    def _render(self) -> None:
        start = self.page * self.page_size
        end = start + self.page_size
        slice_ = self.categories[start:end]
        options: list[discord.SelectOption] = []
        for category in slice_:
            options.append(discord.SelectOption(label=category[:100], value=category))
        if end < len(self.categories):
            options.append(discord.SelectOption(label="➡️ More...", value=MORE))
        if self.page > 0:
            options.append(discord.SelectOption(label="⬅️ Previous...", value=PREV))
        self.select.options = options

    async def _handle(self, interaction: discord.Interaction) -> None:
        from utils.discord_safe import safe_edit_message

        value = self.select.values[0]
        if value == MORE:
            await safe_edit_message(
                interaction,
                view=OrderCategoryView(
                    user_id=self.user_id,
                    categories=self.categories,
                    page=self.page + 1,
                    page_size=self.page_size,
                    on_select=self.on_select,
                ),
            )
            return
        if value == PREV:
            await safe_edit_message(
                interaction,
                view=OrderCategoryView(
                    user_id=self.user_id,
                    categories=self.categories,
                    page=self.page - 1,
                    page_size=self.page_size,
                    on_select=self.on_select,
                ),
            )
            return
        await self.on_select(interaction, value)


class OrderItemView(discord.ui.View):
    def __init__(
        self,
        *,
        user_id: int,
        items: list[dict],
        page: int,
        page_size: int,
        on_pick: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.items = items
        self.page = page
        self.page_size = page_size
        self.on_pick = on_pick
        self.select = discord.ui.Select(
            placeholder="Select item",
            min_values=1,
            max_values=1,
            custom_id="order:select:item",
        )
        self.select.callback = self._handle
        self.add_item(self.select)
        self._render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    def _render(self) -> None:
        start = self.page * self.page_size
        end = start + self.page_size
        slice_ = self.items[start:end]
        options: list[discord.SelectOption] = []
        for it in slice_:
            raw = it.get("item_emoji", "🌟") or "🌟"
            name = str(it.get("item_name", "Item"))
            emoji: str | discord.PartialEmoji | None = raw
            if isinstance(raw, str) and raw.startswith("<"):
                try:
                    emoji = discord.PartialEmoji.from_str(raw)
                except Exception:
                    emoji = None
            price = int(it.get("item_price", 0) or 0)
            options.append(
                discord.SelectOption(
                    label=name[:100],
                    value=str(it.get("item_id")),
                    description="Unavailable" if price <= 0 else f"🪙 {price:,}",
                    emoji=emoji,
                )
            )
        if end < len(self.items):
            options.append(discord.SelectOption(label="➡️ More...", value=MORE))
        if self.page > 0:
            options.append(discord.SelectOption(label="⬅️ Previous...", value=PREV))
        self.select.options = options

    async def _handle(self, interaction: discord.Interaction) -> None:
        from utils.discord_safe import safe_edit_message

        value = self.select.values[0]
        if value == MORE:
            await safe_edit_message(
                interaction,
                view=OrderItemView(
                    user_id=self.user_id,
                    items=self.items,
                    page=self.page + 1,
                    page_size=self.page_size,
                    on_pick=self.on_pick,
                ),
            )
            return
        if value == PREV:
            await safe_edit_message(
                interaction,
                view=OrderItemView(
                    user_id=self.user_id,
                    items=self.items,
                    page=self.page - 1,
                    page_size=self.page_size,
                    on_pick=self.on_pick,
                ),
            )
            return
        await self.on_pick(interaction, value)


class OrderConfirmView(discord.ui.View):
    def __init__(self, on_confirm: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=180)
        self.on_confirm = on_confirm
        self.message: discord.Message | None = None

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success, custom_id="order:confirm")
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        from utils.discord_safe import safe_defer, safe_edit_message

        await safe_defer(interaction)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await safe_edit_message(interaction, view=self)
        await self.on_confirm(interaction)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, custom_id="order:cancel")
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        from utils.discord_safe import safe_defer, safe_edit_message, safe_respond

        await safe_defer(interaction, ephemeral=True)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await safe_edit_message(interaction, view=self)
        await safe_respond(interaction, content="❌ Order canceled.", ephemeral=True)
        self.stop()

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            if self.message:
                await self.message.edit(
                    content="⏰ **Session expired. Please create the order again.**",
                    view=self,
                )
        except NotFound:
            pass
        self.stop()


CLOSE_ORDER_CUSTOM_ID = "orderclose:close"
CONFIRM_TIMEOUT_SECONDS = 30


class OrderCloseConfirmView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=CONFIRM_TIMEOUT_SECONDS)
        self.message: discord.Message | None = None
        token = uuid4().hex[:8]

        yes_btn = discord.ui.Button(
            label="Yes",
            style=discord.ButtonStyle.success,
            custom_id=f"orderclose:yes:{token}",
        )
        no_btn = discord.ui.Button(
            label="No",
            style=discord.ButtonStyle.secondary,
            custom_id=f"orderclose:no:{token}",
        )
        yes_btn.callback = self._yes
        no_btn.callback = self._no
        self.add_item(yes_btn)
        self.add_item(no_btn)

    async def _delete_message(self) -> None:
        if self.message is None:
            return
        try:
            await self.message.delete()
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        await self._delete_message()

    async def _yes(self, interaction: discord.Interaction) -> None:
        from bot.handlers.orders import get_order_handler
        from utils.discord_safe import safe_defer, safe_respond

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Invalid channel.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        self.stop()

        await safe_defer(interaction, ephemeral=True)
        await self._delete_message()

        try:
            await get_order_handler().finalize_close_order(interaction, channel=interaction.channel)
        except Exception:
            log.exception("Failed to close order")
            await safe_respond(interaction, content="❌ Failed to close order.", ephemeral=True)

    async def _no(self, interaction: discord.Interaction) -> None:
        from utils.discord_safe import safe_defer, safe_respond

        for child in self.children:
            child.disabled = True
        self.stop()
        await safe_defer(interaction, ephemeral=True)
        await self._delete_message()
        await safe_respond(interaction, content="❌ Order close cancelled.", ephemeral=True)


class OrderCloseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        btn = discord.ui.Button(
            label="Close Order",
            style=discord.ButtonStyle.danger,
            custom_id=CLOSE_ORDER_CUSTOM_ID,
        )
        btn.callback = self.close_order
        self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    async def close_order(self, interaction: discord.Interaction) -> None:
        from bot.handlers.orders import get_order_handler

        await get_order_handler().handle_close_order_button(interaction)


class RatingWorkerButton(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _handle(self, interaction: discord.Interaction, rating: int) -> None:
        from bot.handlers.orders import get_order_handler
        from utils.discord_safe import safe_defer, safe_respond

        await safe_defer(interaction, ephemeral=True)
        if interaction.message is None:
            await safe_respond(interaction, content="❌ Message not found.", ephemeral=True)
            return
        await get_order_handler().handle_rating(interaction, rating=rating)

    @discord.ui.button(label="⭐ 1", style=discord.ButtonStyle.secondary, custom_id="rating:worker:1")
    async def r1(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, 1)

    @discord.ui.button(label="⭐ 2", style=discord.ButtonStyle.secondary, custom_id="rating:worker:2")
    async def r2(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, 2)

    @discord.ui.button(label="⭐ 3", style=discord.ButtonStyle.secondary, custom_id="rating:worker:3")
    async def r3(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, 3)

    @discord.ui.button(label="⭐ 4", style=discord.ButtonStyle.secondary, custom_id="rating:worker:4")
    async def r4(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, 4)

    @discord.ui.button(label="⭐ 5", style=discord.ButtonStyle.secondary, custom_id="rating:worker:5")
    async def r5(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, 5)
