#app/uis/claimable_button.py
from __future__ import annotations

import time
from typing import Dict, cast, Any

import discord
from discord.ext import commands

from app.uis.claimable_embed import claimable_embed

PAGE_SIZE = 25
COOLDOWN_SECONDS = 60


class ClaimablePaginationView(discord.ui.View):
    def __init__(self, *, page: int = 0) -> None:
        super().__init__(timeout=None)

        self.page = page
        self._cooldowns: Dict[int, float] = {}

        prefix = "claimable"

        self.prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:prev",
        )
        self.refresh_btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id=f"{prefix}:refresh",
        )
        self.next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:next",
        )

        self.prev_btn.callback = self.prev
        self.refresh_btn.callback = self.refresh
        self.next_btn.callback = self.next

        self.add_item(self.prev_btn)
        self.add_item(self.refresh_btn)
        self.add_item(self.next_btn)

    def set_initial_state(self, *, total_items: int) -> None:
        self.prev_btn.disabled = True
        self.next_btn.disabled = total_items <= PAGE_SIZE

    def _max_page(self, total: int) -> int:
        return max(0, (total - 1) // PAGE_SIZE)

    def _sync(self, total: int) -> None:
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= self._max_page(total)

    async def _fetch_entries(self, interaction: discord.Interaction) -> list[dict]:
        bot = cast(commands.Bot, interaction.client)

        cog = bot.get_cog("Claimable")
        if cog is None:
            raise RuntimeError("Claimable cog not loaded")

        cog = cast(Any, cog)  # ⬅️ FIX: no circular import

        return await cog._fetch_claimable()

    async def prev(self, interaction: discord.Interaction) -> None:
        if self.page > 0:
            self.page -= 1

        entries = await self._fetch_entries(interaction)
        self._sync(len(entries))

        await interaction.response.edit_message(
            embed=claimable_embed(
                entries=entries,
                page=self.page,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )

    async def next(self, interaction: discord.Interaction) -> None:
        entries = await self._fetch_entries(interaction)
        max_page = self._max_page(len(entries))

        if self.page < max_page:
            self.page += 1

        self._sync(len(entries))

        await interaction.response.edit_message(
            embed=claimable_embed(
                entries=entries,
                page=self.page,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )

    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        now = time.time()

        last = self._cooldowns.get(user_id)
        if last and (now - last < COOLDOWN_SECONDS):
            return await interaction.followup.send(
                f"⏳ Please wait {int(COOLDOWN_SECONDS - (now - last))} seconds.",
                ephemeral=True,
            )

        self._cooldowns[user_id] = now

        entries = await self._fetch_entries(interaction)
        self.page = 0
        self._sync(len(entries))

        await interaction.edit_original_response(
            embed=claimable_embed(
                entries=entries,
                page=0,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )