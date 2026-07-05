from __future__ import annotations

import logging

import discord

from app.domains.game_domain import PlayableGameType
from app.repositories.game_repo import GameRepository


log = logging.getLogger("discord.game_presenter")


async def edit_game_panel(
    *,
    bot: discord.Client,
    games: GameRepository,
    game_type: PlayableGameType,
    embed: discord.Embed,
    view: discord.ui.View | None,
) -> None:
    panel = await games.get_panel(panel_type="game", game_type=game_type)
    if not panel:
        return

    channel = bot.get_channel(int(panel["channel_id"]))
    if not isinstance(channel, discord.TextChannel):
        return

    try:
        message = await channel.fetch_message(int(panel["message_id"]))
        await message.edit(embed=embed, view=view)
    except discord.HTTPException:
        log.warning("Game panel edit failed | game=%s", game_type)
