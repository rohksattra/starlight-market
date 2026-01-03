# app/uis/order_entry.py
from __future__ import annotations

from typing import Callable, Awaitable

import discord

from utils.interaction_safe import safe_defer


class OrderEntryView(discord.ui.View):
    def __init__(self, on_start: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=None)
        self.on_start = on_start

    @discord.ui.button(label="🛒 Order Now", style=discord.ButtonStyle.primary, custom_id="order:entry:start")
    async def order_now(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await safe_defer(interaction, ephemeral=True)
        await self.on_start(interaction)
