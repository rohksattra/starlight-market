# app/uis/order_confirm_view.py
from __future__ import annotations

from typing import Callable, Awaitable

import discord
from discord.errors import NotFound

from utils.interaction_safe import (
    safe_defer,
    safe_edit_message,
    safe_respond,
)


class OrderConfirmView(discord.ui.View):
    def __init__(self, on_confirm: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=180)
        self.on_confirm = on_confirm
        self.message: discord.Message | None = None

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await safe_defer(interaction)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await safe_edit_message(interaction, view=self)
        await self.on_confirm(interaction)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
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
                await self.message.edit(content="⏰ **Session expired. Please create the order again.**", view=self)
        except NotFound:
            pass
        self.stop()
