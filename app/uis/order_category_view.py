# app/uis/order_category_view.py
from __future__ import annotations

from typing import Callable, Awaitable

import discord

from utils.interaction_safe import safe_edit_message


MORE = "__more__"
PREV = "__prev__"


class OrderCategoryView(discord.ui.View):
    def __init__(
        self, *, user_id: int, categories: list[str], page: int, page_size: int, on_select: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=180)
        if not categories:
            raise ValueError("categories cannot be empty")
        self.user_id = user_id
        self.categories = categories
        self.page = page
        self.page_size = page_size
        self.on_select = on_select
        self.select = discord.ui.Select(placeholder="Select category", min_values=1, max_values=1)
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
        value = self.select.values[0]
        if value == MORE:
            await safe_edit_message(interaction, view=OrderCategoryView(
                    user_id=self.user_id,
                    categories=self.categories,
                    page=self.page + 1,
                    page_size=self.page_size,
                    on_select=self.on_select,
                ))
            return
        if value == PREV:
            await safe_edit_message(interaction, view=OrderCategoryView(
                    user_id=self.user_id,
                    categories=self.categories,
                    page=self.page - 1,
                    page_size=self.page_size,
                    on_select=self.on_select,
                ))
            return
        await self.on_select(interaction, value)
