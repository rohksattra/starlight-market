from __future__ import annotations

import re
from typing import Dict, cast

import discord
from discord.ext import commands

from app.domains.game_domain import GAME_TITLES, GameType
from app.handlers.game import get_game_handler
from app.views.game_leaderboard_embed import game_leaderboard_embed
from utils.interaction_safe import safe_defer, safe_edit_message, safe_respond
from utils.ui_cooldown import begin_refresh_cooldown, clear_refresh_cooldown


COOLDOWN_SECONDS = 60
PAGE_SIZE = 25
MAX_ITEMS = 100


class GameLeaderboardPaginationView(discord.ui.View):
    def __init__(self, *, game_type: GameType, page: int = 0) -> None:
        super().__init__(timeout=None)
        self.game_type: GameType = game_type
        self.page = page
        self._cooldowns: Dict[int, float] = {}

        prefix = f"game_leaderboard:{self.game_type}"

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

    def _sync_page_from_message(self, interaction: discord.Interaction) -> None:
        message = interaction.message
        if message is None or not message.embeds:
            return
        footer = message.embeds[0].footer.text or ""
        match = re.search(r"Page\s+(\d+)/(\d+)", footer)
        if not match:
            return
        self.page = max(0, int(match.group(1)) - 1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    def _sync_game_type_from_interaction(self, interaction: discord.Interaction) -> None:
        data = interaction.data or {}
        custom_id = data.get("custom_id")
        if not isinstance(custom_id, str):
            return
        parts = custom_id.split(":")
        if len(parts) >= 3 and parts[1] in GAME_TITLES:
            self.game_type = cast(GameType, parts[1])

    async def _fetch_entries(self, interaction: discord.Interaction) -> list[dict]:
        self._sync_game_type_from_interaction(interaction)
        self._sync_page_from_message(interaction)

        bot = cast(commands.Bot, interaction.client)
        return await get_game_handler(bot).fetch_game_leaderboard(self.game_type)

    async def prev(self, interaction: discord.Interaction) -> None:
        entries = await self._fetch_entries(interaction)
        if self.page > 0:
            self.page -= 1
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        user_id = interaction.user.id
        remaining = begin_refresh_cooldown(self._cooldowns, user_id, seconds=COOLDOWN_SECONDS)
        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            entries = await self._fetch_entries(interaction)
            self._sync_buttons(total_items=len(entries))
            await safe_edit_message(
                interaction,
                embed=game_leaderboard_embed(
                    game_type=self.game_type,
                    entries=entries,
                    page=self.page,
                    page_size=PAGE_SIZE,
                ),
                view=self,
            )
        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)
            await safe_respond(
                interaction,
                content="❌ Failed to refresh leaderboard.",
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
            embed=game_leaderboard_embed(
                game_type=self.game_type,
                entries=entries,
                page=self.page,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )
