# app/uis/order_item.py
from __future__ import annotations

from typing import Callable, Awaitable

import discord

from utils.interaction_safe import safe_edit_message


MORE = "__more__"
PREV = "__prev__"


class OrderItemView(discord.ui.View):
    def __init__(
        self, *, user_id: int, items: list[dict], page: int, page_size: int, on_pick: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=180)
        if not items:
            raise ValueError("items cannot be empty")
        self.user_id = user_id
        self.items = items
        self.page = page
        self.page_size = page_size
        self.on_pick = on_pick
        self.select = discord.ui.Select(placeholder="Select item", min_values=1, max_values=1)
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
            options.append(
                discord.SelectOption(
                    label=str(it.get("item_name", "Item"))[:100],
                    value=str(it.get("item_id")),
                    description=f"🪙 {int(it.get('item_price', 0)):,}",
                )
            )
        if end < len(self.items):
            options.append(discord.SelectOption(label="➡️ More...", value=MORE))
        if self.page > 0:
            options.append(discord.SelectOption(label="⬅️ Previous...", value=PREV))
        self.select.options = options

    async def _handle(self, interaction: discord.Interaction) -> None:
        value = self.select.values[0]
        if value == MORE:
            await safe_edit_message(interaction, view=OrderItemView(
                    user_id=self.user_id,
                    items=self.items,
                    page=self.page + 1,
                    page_size=self.page_size,
                    on_pick=self.on_pick,
                ),
            )
            return
        if value == PREV:
            await safe_edit_message(interaction, view=OrderItemView(
                    user_id=self.user_id,
                    items=self.items,
                    page=self.page - 1,
                    page_size=self.page_size,
                    on_pick=self.on_pick,
                ),
            )
            return
        await self.on_pick(interaction, value)
