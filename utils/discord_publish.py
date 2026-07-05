from __future__ import annotations

import discord


async def publish_news(message: discord.Message) -> None:
    channel = message.channel

    if not isinstance(channel, discord.TextChannel):
        return

    if not channel.is_news():
        return

    try:
        await message.publish()
    except discord.HTTPException:
        pass