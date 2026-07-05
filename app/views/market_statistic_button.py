from __future__ import annotations

import time
from typing import Dict

import discord

from app.handlers.market_statistic import get_market_statistic_handler

from app.views.market_statistic_embed import market_statistic_embed
from utils.interaction_safe import safe_defer, safe_edit_message, safe_respond


COOLDOWN_SECONDS = 60


class MarketStatisticRefreshView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

        self._cooldowns: Dict[int, float] = {}

        self.refresh_btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id="market_stat:refresh",
        )
        self.refresh_btn.callback = self.refresh
        self.add_item(self.refresh_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    async def _fetch_embed(self, interaction: discord.Interaction) -> discord.Embed:
        if interaction.guild is None:
            raise RuntimeError("Guild required for market statistics")
        data = await get_market_statistic_handler().fetch_stat_data(interaction.guild)
        return market_statistic_embed(**data)

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
            embed = await self._fetch_embed(interaction)
            await safe_edit_message(interaction, embed=embed, view=self)
        except Exception:
            self._cooldowns.pop(user_id, None)
            await safe_respond(
                interaction,
                content="❌ Failed to refresh market statistics.",
                ephemeral=True,
            )

