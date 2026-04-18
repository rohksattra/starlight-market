# app/uis/price_button.py
from __future__ import annotations

import time
from typing import Dict

import discord

from app.services.item_service import ItemService
from app.uis.price_embed import price_embed
from utils.interaction_safe import safe_defer, safe_edit_message, safe_respond


PAGE_SIZE = 25
COOLDOWN_SECONDS = 60


class PricePaginationView(discord.ui.View):
    def __init__(self, *, category: str, page: int = 0) -> None:
        super().__init__(timeout=None)
        self.category = category
        self.page = page
        self._cooldowns: Dict[int, float] = {}
        self.item_serv = ItemService()

        prefix = f"price:{category}"

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

    async def _fetch_items(self) -> list[dict]:
        return await self.item_serv.list_item_price_by_category(self.category)

    async def prev(self, interaction: discord.Interaction) -> None:
        if self.page > 0:
            self.page -= 1

        items = await self._fetch_items()
        self._sync_buttons(total_items=len(items))

        await interaction.response.edit_message(
            embed=price_embed(
                category=self.category,
                items=items,
                page=self.page,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )

    async def next(self, interaction: discord.Interaction) -> None:
        items = await self._fetch_items()
        max_page = self._max_page(total_items=len(items))

        if self.page < max_page:
            self.page += 1

        self._sync_buttons(total_items=len(items))

        await interaction.response.edit_message(
            embed=price_embed(
                category=self.category,
                items=items,
                page=self.page,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )

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
            items = await self._fetch_items()
            self.page = 0
            self._sync_buttons(total_items=len(items))

            await safe_edit_message(
                interaction,
                embed=price_embed(
                    category=self.category,
                    items=items,
                    page=self.page,
                    page_size=PAGE_SIZE,
                ),
                view=self,
            )
        except Exception:
            self._cooldowns.pop(user_id, None)
            await safe_respond(
                interaction,
                content="❌ Failed to refresh price list.",
                ephemeral=True,
            )