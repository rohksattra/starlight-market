from __future__ import annotations

from typing import Any

import discord
from discord.ext import commands

from app.domains.game_domain import GameType


class GameHandler:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._runtime = None

    @property
    def runtime(self):
        if self._runtime is None:
            from app.discord.game_runtime import GameRuntimeService

            self._runtime = GameRuntimeService(self.bot)
        return self._runtime

    @property
    def game_serv(self):
        return self.runtime.game_serv

    @property
    def games(self):
        return self.runtime.games

    async def fetch_game_leaderboard(self, game_type: GameType) -> list[dict[str, Any]]:
        from app.views.game_leaderboard_button import MAX_ITEMS

        rows = await self.game_serv.fetch_leaderboard(game_type=game_type, limit=MAX_ITEMS)
        guild = self.bot.guilds[0] if self.bot.guilds else None

        for row in rows:
            name = "Unknown"
            if guild is not None:
                member = guild.get_member(int(row["id"]))
                if member:
                    name = member.display_name
            row["name"] = name

        return rows

    async def send_leaderboard_panel(
        self,
        *,
        channel: discord.TextChannel,
        game_type: GameType,
    ) -> discord.Message:
        from app.views.game_leaderboard_button import GameLeaderboardPaginationView, PAGE_SIZE
        from app.views.game_leaderboard_embed import game_leaderboard_embed

        entries = await self.fetch_game_leaderboard(game_type)
        view = GameLeaderboardPaginationView(game_type=game_type)
        view.set_initial_state(total_items=len(entries))

        message = await channel.send(
            embed=game_leaderboard_embed(
                game_type=game_type,
                entries=entries,
                page=0,
                page_size=PAGE_SIZE,
            ),
            view=view,
        )

        await self.games.upsert_panel(
            panel_type="leaderboard",
            game_type=game_type,
            channel_id=str(channel.id),
            message_id=str(message.id),
        )

        return message


_handlers: dict[int, GameHandler] = {}


def get_game_handler(bot: commands.Bot) -> GameHandler:
    key = id(bot)
    if key not in _handlers:
        _handlers[key] = GameHandler(bot)
    return _handlers[key]
