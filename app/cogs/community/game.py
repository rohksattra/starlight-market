from __future__ import annotations

import logging
from typing import Any, List, cast

import discord
from discord import app_commands
from discord.ext import commands

from app.domains.enums.role_enum import STAFF_ROLE
from app.domains.game_domain import GAME_TYPES, GameType, PlayableGameType
from app.services.game_constants import (
    BATTLE_GAME_TYPES,
    PLAYABLE_GAME_CHANNEL_IDS,
)
from app.handlers.game import get_game_handler
from app.views.game_embed import (
    battle_embed,
    counting_embed,
    daily_embed,
    guess_embed,
    reaction_embed,
    scramble_embed,
    treasure_embed,
    wordchain_embed,
)
from app.views.game_view import (
    BattleGameView,
    CountingGameView,
    DailyGameView,
    GuessGameView,
    ReactionRushGameView,
    ScrambleGameView,
    TreasureGameView,
    WordChainGameView,
)
from core.role_map import has_any_role
from utils.interaction_safe import safe_defer, safe_respond


log = logging.getLogger("cogs.game")


class Game(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.handler = get_game_handler(bot)
        self.runtime = self.handler.runtime
        self.game_serv = self.handler.game_serv
        self.games = self.handler.games

    async def cog_load(self) -> None:
        await self.runtime.recover_reaction_auto_reset()
        for game_type in BATTLE_GAME_TYPES:
            await self.runtime.recover_battle_auto_reset(game_type)

    def _ensure_staff(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        return has_any_role(interaction.user, STAFF_ROLE)

    async def _fetch_game_leaderboard(self, game_type: GameType) -> List[dict[str, Any]]:
        return await self.handler.fetch_game_leaderboard(game_type)

    def _configured_game_channel_id(self, game_type: PlayableGameType) -> int:
        return PLAYABLE_GAME_CHANNEL_IDS[game_type]

    def _resolve_playable_channel(
        self,
        guild: discord.Guild,
        game_type: PlayableGameType,
    ) -> discord.TextChannel | None:
        channel = guild.get_channel(self._configured_game_channel_id(game_type))
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _send_leaderboard_panel(
        self,
        *,
        channel: discord.TextChannel,
        game_type: GameType,
    ) -> discord.Message:
        return await self.handler.send_leaderboard_panel(channel=channel, game_type=game_type)

    async def _send_game_panel(
        self,
        *,
        channel: discord.TextChannel,
        game_type: PlayableGameType,
    ) -> discord.Message:
        if game_type == "counting":
            state = await self.runtime.state("counting") or await self.runtime.reset_counting()
            embed = counting_embed(question=str(state["question"]))
            view = CountingGameView()

        elif game_type == "wordchain":
            state = await self.runtime.state("wordchain") or await self.runtime.reset_wordchain()
            embed = wordchain_embed(
                word=str(state["word"]),
                used_count=int(state.get("used_count", len(state.get("used_words", []))) or 0),
            )
            view = WordChainGameView()

        elif game_type == "guess":
            state = await self.runtime.state("guess") or await self.runtime.reset_guess()
            embed = guess_embed(active=bool(state.get("active", True)))
            view = GuessGameView()

        elif game_type == "treasure":
            embed = treasure_embed()
            view = TreasureGameView()

        elif game_type == "reaction":
            state = await self.runtime.state("reaction") or await self.runtime.reset_reaction()
            claimed_count = len(state.get("claimed_user_ids", []))
            embed = reaction_embed(claimed_count=claimed_count)
            view = ReactionRushGameView(click_disabled=claimed_count >= 3)

        elif game_type == "scramble":
            state = await self.runtime.state("scramble") or await self.runtime.reset_scramble()
            embed = scramble_embed(
                scrambled=str(state["scrambled"]),
                hint_image_url=str(state.get("hint_image_url", "")),
            )
            view = ScrambleGameView()

        elif game_type == "daily":
            embed = daily_embed()
            view = DailyGameView()

        elif game_type in {"monster", "boss"}:
            state = await self.runtime.state(game_type) or await self.runtime.reset_enemy(game_type=game_type)
            embed = battle_embed(game_type=game_type, state=state)
            view = BattleGameView(game_type=game_type)

        else:
            raise ValueError("Unknown game type")

        message = await channel.send(embed=embed, view=view)

        await self.games.upsert_panel(
            panel_type="game",
            game_type=game_type,
            channel_id=str(channel.id),
            message_id=str(message.id),
        )

        return message

    @app_commands.command(name="game-panel", description="Post a persistent game panel in this channel.")
    @app_commands.describe(game="Game panel to post")
    @app_commands.choices(
        game=[
            app_commands.Choice(name="Counting", value="counting"),
            app_commands.Choice(name="Word Chain", value="wordchain"),
            app_commands.Choice(name="Guess the Number", value="guess"),
            app_commands.Choice(name="Treasure Hunt", value="treasure"),
            app_commands.Choice(name="Boss Battle", value="boss"),
            app_commands.Choice(name="Reaction Rush", value="reaction"),
            app_commands.Choice(name="Scramble Word", value="scramble"),
            app_commands.Choice(name="Daily Check-In", value="daily"),
            app_commands.Choice(name="Monster Hunt", value="monster"),
        ]
    )
    async def game_panel(self, interaction: discord.Interaction, game: app_commands.Choice[str]) -> None:
        if not self._ensure_staff(interaction):
            await safe_respond(
                interaction,
                content="❌ You don't have permission to use this command.",
                ephemeral=True,
            )
            return

        if interaction.guild is None:
            await safe_respond(
                interaction,
                content="❌ Use this command in a server.",
                ephemeral=True,
            )
            return

        game_type = cast(PlayableGameType, game.value)

        if game_type not in GAME_TYPES:
            await safe_respond(
                interaction,
                content="❌ Unknown game type.",
                ephemeral=True,
            )
            return

        channel = self._resolve_playable_channel(interaction.guild, game_type)
        if channel is None:
            await safe_respond(
                interaction,
                content=f"❌ Channel for **{game.name}** is not configured or not found.",
                ephemeral=True,
            )
            return

        await safe_defer(interaction, ephemeral=True)

        await self._send_game_panel(
            channel=channel,
            game_type=game_type,
        )

        await safe_respond(
            interaction,
            content=f"✅ **{game.name}** panel posted in {channel.mention}.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Game(bot))