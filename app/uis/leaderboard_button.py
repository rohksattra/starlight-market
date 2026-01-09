# app/uis/leaderboard_button.py
from __future__ import annotations

import time
from typing import Literal, Dict, TYPE_CHECKING, cast

import discord
from discord.ext import commands

from app.uis.leaderboard_embed import leaderboard_embed
from utils.interaction_safe import (
    safe_defer,
    safe_edit_message,
    safe_respond,
)

if TYPE_CHECKING:
    from app.cogs.leaderboard import Leaderboard


LBType = Literal["worker", "customer", "item"]

COOLDOWN_SECONDS = 60
PAGE_SIZE = 25
MAX_ITEMS = 100


class LeaderboardPaginationView(discord.ui.View):
    def __init__(self, *, lb_type: LBType, title: str, entries: list[dict]) -> None:
        super().__init__(timeout=None)
        self.lb_type: LBType = lb_type
        self.title = title
        self.entries = entries[:MAX_ITEMS]
        self.page = 0
        self._cooldowns: Dict[int, float] = {}
        self._sync_buttons()

    def _max_page(self) -> int:
        return max(0, (len(self.entries) - 1) // PAGE_SIZE)

    def _sync_buttons(self) -> None:
        self.prev.disabled = self.page <= 0
        self.next.disabled = self.page >= self._max_page()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.page > 0:
            self.page -= 1
        self._sync_buttons()
        await self._update(interaction)

    @discord.ui.button(label="🔄", style=discord.ButtonStyle.success)
    async def refresh(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
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
            bot = cast(commands.Bot, interaction.client)
            cog = bot.get_cog("Leaderboard")
            if cog is None:
                raise RuntimeError("Leaderboard cog missing")
            leaderboard = cast("Leaderboard", cog)
            if self.lb_type == "worker":
                self.entries = (await leaderboard._fetch_worker())[:MAX_ITEMS]
            elif self.lb_type == "customer":
                self.entries = (await leaderboard._fetch_customer())[:MAX_ITEMS]
            else:
                self.entries = (await leaderboard._fetch_item())[:MAX_ITEMS]
            self.page = 0
            self._sync_buttons()
            await safe_edit_message(
                interaction,
                embed=leaderboard_embed(
                    title=self.title,
                    entries=self.entries,
                    lb_type=cast(LBType, self.lb_type),
                    page=self.page,
                    page_size=PAGE_SIZE,
                ),
                view=self,
            )
        except Exception:
            self._cooldowns.pop(user_id, None)
            await safe_respond(
                interaction,
                content="❌ Failed to refresh leaderboard.",
                ephemeral=True,
            )

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.page < self._max_page():
            self.page += 1
        self._sync_buttons()
        await self._update(interaction)

    async def _update(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=leaderboard_embed(
                title=self.title,
                entries=self.entries,
                lb_type=cast(LBType, self.lb_type),
                page=self.page,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )
