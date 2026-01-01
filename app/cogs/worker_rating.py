# app/cogs/worker_rating.py
from __future__ import annotations

import discord
from discord.ext import commands

from app.services.worker_rating_service import WorkerRatingService
from utils.interaction_safe import safe_defer, safe_edit_message, safe_respond


class WorkerRating(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.worker_rating_serv = WorkerRatingService()

    async def handle_rating(self, interaction: discord.Interaction, *, rating: int) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid user.", ephemeral=True)
            return
        if interaction.message is None:
            await safe_respond(interaction, content="❌ Message not found.", ephemeral=True)
            return
        transaction_id = str(interaction.message.id)
        try:
            await self.worker_rating_serv.submit_rating(transaction_id=transaction_id, customer_id=str(interaction.user.id), rating=rating)
        except PermissionError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            await self._disable_buttons(interaction)
            return
        except RuntimeError:
            await safe_respond(interaction, content="❌ Failed to submit rating.", ephemeral=True)
            return
        await self._disable_buttons(interaction)
        await safe_respond(interaction, content=f"✅ Thank you! You rated the worker **{rating}⭐**.", ephemeral=True)


    async def _disable_buttons(self, interaction: discord.Interaction) -> None:
        message = interaction.message
        if message is None or not message.components:
            return
        try:
            view = discord.ui.View.from_message(message)
        except Exception:
            return
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await safe_edit_message(interaction, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WorkerRating(bot))
