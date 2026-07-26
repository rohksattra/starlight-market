from __future__ import annotations

import discord

from app.handlers.worker_rating import get_worker_rating_handler
from utils.interaction_safe import safe_defer, safe_respond


class RatingWorkerButton(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _handle(self, interaction: discord.Interaction, rating: int) -> None:
        await safe_defer(interaction, ephemeral=True)
        if interaction.message is None:
            await safe_respond(interaction, content="❌ Message not found.", ephemeral=True)
            return
        await get_worker_rating_handler().handle_rating(interaction, rating=rating)

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
