from __future__ import annotations

import logging

import discord
from discord.ext import commands

from app.handlers.game_messages import get_game_message_handler


log = logging.getLogger("events.messages")


class MessageEvents(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def on_game_message(self, message: discord.Message) -> None:
        await get_game_message_handler(self.bot).handle_message(message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MessageEvents(bot))
