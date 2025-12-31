# app/uis/price_button.py
from __future__ import annotations

import time
from typing import Dict

import discord

from app.services.item_service import ItemService
from app.uis.price_embed import price_embed
from utils.interaction_safe import safe_defer, safe_edit_message, safe_respond


COOLDOWN_SECONDS = 60


class PriceRefreshView(discord.ui.View):
    def __init__(self, *, category: str) -> None:
        super().__init__(timeout=None)
        self.category = category
        self._cooldowns: Dict[int, float] = {}
        self.item_serv = ItemService()
        self.refresh.custom_id = f"price:refresh:{category}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    @discord.ui.button(label="🔄", style=discord.ButtonStyle.success)
    async def refresh(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await safe_defer(interaction, ephemeral=True)
        if interaction.message is None:
            await safe_respond(interaction, content="❌ Price message not found.", ephemeral=True)
            return
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
            items = await self.item_serv.list_item_price_by_category(self.category)
            embed = price_embed(category=self.category, items=items)
            await safe_edit_message(interaction, embed=embed, view=self)
        except discord.HTTPException:
            self._cooldowns.pop(user_id, None)
            await safe_respond(
                interaction,
                content="⚠️ Failed to refresh price list due to a Discord error.",
                ephemeral=True,
            )
        except Exception:
            self._cooldowns.pop(user_id, None)
            await safe_respond(
                interaction,
                content="❌ An unexpected error occurred while refreshing the price list.",
                ephemeral=True,
            )
