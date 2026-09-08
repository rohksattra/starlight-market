"""Discord event listeners for community game messages."""
from __future__ import annotations

import discord
from discord.ext import commands

from bot.handlers.games import get_game_message_handler


class MessageEvents(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.game_messages = get_game_message_handler(bot)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        await self.game_messages.handle_message(message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MessageEvents(bot))
