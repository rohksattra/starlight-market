# app/uis/order_quantity.py
from __future__ import annotations

from typing import Callable, Awaitable

import discord

from utils.interaction_safe import safe_respond


class QuantityModal(discord.ui.Modal, title="Quantity"):
    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="Enter number",
        required=True,
    )

    def __init__(self, on_submit: Callable[[discord.Interaction, int], Awaitable[None]]) -> None:
        super().__init__()
        self._cb = on_submit

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            qty = int(self.quantity.value)
        except ValueError:
            await safe_respond(interaction, content="❌ Quantity must be a number.", ephemeral=True)
            return
        if qty <= 0:
            await safe_respond(interaction, content="❌ Quantity must be greater than 0.", ephemeral=True)
            return
        await self._cb(interaction, qty)
