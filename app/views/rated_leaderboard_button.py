from __future__ import annotations

import time
from typing import Dict

import discord

from app.handlers.leaderboard import get_leaderboard_handler, resolve_guild

from app.views.rated_leaderboard_embed import rated_leaderboard_embed
from utils.interaction_safe import safe_defer, safe_edit_message, safe_respond


COOLDOWN_SECONDS = 60
PAGE_SIZE = 25
MAX_ITEMS = 100


class RatedLeaderboardPaginationView(discord.ui.View):
    def __init__(self, *, page: int = 0) -> None:
        super().__init__(timeout=None)
        self.page = page
        self._cooldowns: Dict[int, float] = {}

        prefix = "leaderboard:rated"

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

    def _max_page(self, *, total_items: int) -> int:
        return max(0, (total_items - 1) // PAGE_SIZE)

    def _sync_buttons(self, *, total_items: int) -> None:
        max_page = self._max_page(total_items=total_items)
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= max_page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    async def _fetch_entries(self, interaction: discord.Interaction) -> list[dict]:
        guild = resolve_guild(interaction)
        return (await get_leaderboard_handler().fetch_rated_workers(guild))[:MAX_ITEMS]

    async def prev(self, interaction: discord.Interaction) -> None:
        if self.page > 0:
            self.page -= 1
        entries = await self._fetch_entries(interaction)
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        user_id = interaction.user.id
        now = time.time()

        last_used = self._cooldowns.get(user_id)
        if last_used is not None:
            remaining = COOLDOWN_SECONDS - (now - last_used)
            if remaining > 0:
                await safe_respond(
                    interaction,
                    content=f"⏳ Please wait **{int(remaining)} seconds** before refreshing again.",
                    ephemeral=True,
                )
                return

        self._cooldowns[user_id] = now
        try:
            entries = await self._fetch_entries(interaction)
            self.page = 0
            self._sync_buttons(total_items=len(entries))
            await safe_edit_message(
                interaction,
                embed=rated_leaderboard_embed(
                    title="⭐ Top Rated Workers",
                    entries=entries,
                    page=self.page,
                    page_size=PAGE_SIZE,
                ),
                view=self,
            )
        except Exception:
            self._cooldowns.pop(user_id, None)
            await safe_respond(
                interaction,
                content="❌ Failed to refresh rated leaderboard.",
                ephemeral=True,
            )

    async def next(self, interaction: discord.Interaction) -> None:
        entries = await self._fetch_entries(interaction)
        max_page = self._max_page(total_items=len(entries))
        if self.page < max_page:
            self.page += 1
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def _update(self, interaction: discord.Interaction, *, entries: list[dict]) -> None:
        await safe_edit_message(
            interaction,
            embed=rated_leaderboard_embed(
                title="⭐ Top Rated Workers",
                entries=entries,
                page=self.page,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )

