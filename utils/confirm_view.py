from __future__ import annotations

import asyncio

import discord

from utils.interaction_safe import safe_edit_message


class ConfirmView(discord.ui.View):
    def __init__(self, *, author_id: int, timeout_seconds: int = 30) -> None:
        super().__init__(timeout=timeout_seconds)
        self._author_id = author_id
        self._future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self._author_id

    async def on_timeout(self) -> None:
        if not self._future.done():
            self._future.set_result(False)

    def _lock(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    async def wait_result(self) -> bool:
        return await self._future

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self._future.done():
            self._future.set_result(True)
        self._lock()
        await safe_edit_message(interaction, view=self)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self._future.done():
            self._future.set_result(False)
        self._lock()
        await safe_edit_message(interaction, view=self)
