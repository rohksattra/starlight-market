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
    def __init__(self, *, lb_type: LBType, title: str, page: int = 0) -> None:
        super().__init__(timeout=None)
        self.lb_type: LBType = lb_type
        self.title = title
        self.page = page
        self._cooldowns: Dict[int, float] = {}
        prefix = f"leaderboard:{self.lb_type}"
        self.prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, custom_id=f"{prefix}:prev")
        self.refresh_btn = discord.ui.Button(label="🔄", style=discord.ButtonStyle.success, custom_id=f"{prefix}:refresh")
        self.next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, custom_id=f"{prefix}:next")
        self.prev_btn.callback = self.prev
        self.refresh_btn.callback = self.refresh
        self.next_btn.callback = self.next
        self.add_item(self.prev_btn)
        self.add_item(self.refresh_btn)
        self.add_item(self.next_btn)

    def _max_page(self, *, total_items: int) -> int:
        return max(0, (total_items - 1) // PAGE_SIZE)

    def _sync_buttons(self, *, total_items: int) -> None:
        max_page = self._max_page(total_items=total_items)
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= max_page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    def _sync_lb_type_from_interaction(self, interaction: discord.Interaction) -> None:
        data = interaction.data or {}
        custom_id = data.get("custom_id")
        if not isinstance(custom_id, str):
            return
        parts = custom_id.split(":")
        if len(parts) >= 3:
            lb_type = parts[1]
            if lb_type in ("worker", "customer", "item"):
                self.lb_type = cast(LBType, lb_type)

    async def _fetch_entries(self, interaction: discord.Interaction) -> list[dict]:
        self._sync_lb_type_from_interaction(interaction)
        bot = cast(commands.Bot, interaction.client)
        cog = bot.get_cog("Leaderboard")
        if cog is None:
            raise RuntimeError("Leaderboard cog missing")
        leaderboard = cast("Leaderboard", cog)
        if self.lb_type == "worker":
            return (await leaderboard._fetch_worker())[:MAX_ITEMS]
        if self.lb_type == "customer":
            return (await leaderboard._fetch_customer())[:MAX_ITEMS]
        return (await leaderboard._fetch_item())[:MAX_ITEMS]

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
                await safe_respond(interaction, content=f"⏳ Please wait **{int(remaining)} seconds** before refreshing again.", ephemeral=True)
                return
        self._cooldowns[user_id] = now
        try:
            entries = await self._fetch_entries(interaction)
            self.page = 0
            self._sync_buttons(total_items=len(entries))
            await safe_edit_message(
                interaction,
                embed=leaderboard_embed(title=self.title, entries=entries, lb_type=cast(LBType, self.lb_type), page=self.page, page_size=PAGE_SIZE),
                view=self,
            )
        except Exception:
            self._cooldowns.pop(user_id, None)
            await safe_respond(interaction, content="❌ Failed to refresh leaderboard.", ephemeral=True)

    async def next(self, interaction: discord.Interaction) -> None:
        entries = await self._fetch_entries(interaction)
        max_page = self._max_page(total_items=len(entries))
        if self.page < max_page:
            self.page += 1
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def _update(self, interaction: discord.Interaction, *, entries: list[dict]) -> None:
        await interaction.response.edit_message(
            embed=leaderboard_embed(title=self.title, entries=entries, lb_type=cast(LBType, self.lb_type), page=self.page, page_size=PAGE_SIZE),
            view=self,
        )
