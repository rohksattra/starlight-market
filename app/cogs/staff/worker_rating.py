from __future__ import annotations

import discord
from discord.ext import commands

from app.handlers.worker_rating import get_worker_rating_handler


class WorkerRating(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.handler = get_worker_rating_handler()

    async def handle_rating(self, interaction: discord.Interaction, *, rating: int) -> None:
        await self.handler.handle_rating(interaction, rating=rating)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WorkerRating(bot))
