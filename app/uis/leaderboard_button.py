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


class LeaderboardRefreshView(discord.ui.View):
    def __init__(self, *, lb_type: LBType, title: str) -> None:
        super().__init__(timeout=None)
        self.lb_type: LBType = lb_type
        self.title: str = title
        self._cooldowns: Dict[int, float] = {}
        self.refresh.custom_id = f"leaderboard:refresh:{lb_type}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    @discord.ui.button(label="🔄", style=discord.ButtonStyle.success)
    async def refresh(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await safe_defer(interaction, ephemeral=True)
        if interaction.message is None:
            await safe_respond(interaction, content="❌ Leaderboard message not found.", ephemeral=True)
            return
        user_id = interaction.user.id
        now = time.time()
        last_used = self._cooldowns.get(user_id)
        if last_used is not None:
            remaining = COOLDOWN_SECONDS - (now - last_used)
            if remaining > 0:
                await safe_respond(interaction, content=(
                        f"⏳ Please wait **{int(remaining)} seconds** "
                        "before refreshing again."
                    ), ephemeral=True)
                return
        self._cooldowns[user_id] = now
        try:
            bot = cast(commands.Bot, interaction.client)
            cog = bot.get_cog("Leaderboard")
            if cog is None:
                self._cooldowns.pop(user_id, None)
                await safe_respond(interaction, content="❌ Leaderboard system is unavailable.", ephemeral=True)
                return
            leaderboard = cast("Leaderboard", cog)
            if self.lb_type == "worker":
                data = await leaderboard._fetch_worker()
            elif self.lb_type == "customer":
                data = await leaderboard._fetch_customer()
            else:
                data = await leaderboard._fetch_item()
            embed = leaderboard_embed(title=self.title, entries=data, lb_type=self.lb_type)
            await safe_edit_message(interaction, embed=embed, view=self)
        except discord.HTTPException:
            self._cooldowns.pop(user_id, None)
            await safe_respond(interaction, content=(
                    "⚠️ Failed to refresh leaderboard due to a Discord error. "
                    "Please try again."
                ), ephemeral=True)
        except Exception:
            self._cooldowns.pop(user_id, None)
            await safe_respond(interaction, content=(
                    "❌ An unexpected error occurred while refreshing the leaderboard."
                ), ephemeral=True)
