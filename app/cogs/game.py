from __future__ import annotations

import logging
import re
from typing import Any, List, cast

import discord
from discord import app_commands
from discord.ext import commands

from app.domains.enums.role_enum import STAFF_ROLE
from app.domains.game_domain import GAME_TYPES, LEADERBOARD_TYPES, GameType, PlayableGameType
from app.services.game_constants import (
    BATTLE_GAME_TYPES,
    PLAYABLE_GAME_CHANNEL_IDS,
    TYPED_ANSWER_CHANNEL_MAP,
)
from app.services.game_runtime_service import GameRuntimeService
from app.uis.game_embed import (
    battle_embed,
    counting_embed,
    daily_embed,
    guess_embed,
    reaction_embed,
    scramble_embed,
    treasure_embed,
    wordchain_embed,
)
from app.uis.game_leaderboard_button import GameLeaderboardPaginationView, MAX_ITEMS, PAGE_SIZE
from app.uis.game_leaderboard_embed import game_leaderboard_embed
from app.uis.game_view import (
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
from utils.scheduled_message_delete import schedule_message_delete


log = logging.getLogger("cogs.game")


def _normalize_answer(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _counting_reward(question: str) -> int:
    if "*" in question or "/" in question:
        return 5

    return 2


class Game(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.runtime = GameRuntimeService(bot)
        self.game_serv = self.runtime.game_serv
        self.games = self.runtime.games

    async def cog_load(self) -> None:
        self.register_persistent_views()
        await self.runtime.recover_reaction_auto_reset()
        for game_type in BATTLE_GAME_TYPES:
            await self.runtime.recover_battle_auto_reset(game_type)

    def register_persistent_views(self) -> None:
        self.bot.add_view(CountingGameView())
        self.bot.add_view(WordChainGameView())
        self.bot.add_view(GuessGameView())
        self.bot.add_view(TreasureGameView())
        self.bot.add_view(ReactionRushGameView())
        self.bot.add_view(ScrambleGameView())
        self.bot.add_view(DailyGameView())
        self.bot.add_view(BattleGameView(game_type="monster"))
        self.bot.add_view(BattleGameView(game_type="boss"))

        for game_type in LEADERBOARD_TYPES:
            self.bot.add_view(GameLeaderboardPaginationView(game_type=game_type))

    def _ensure_staff(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        return has_any_role(interaction.user, STAFF_ROLE)

    async def _fetch_game_leaderboard(self, game_type: GameType) -> List[dict[str, Any]]:
        rows = await self.game_serv.fetch_leaderboard(game_type=game_type, limit=MAX_ITEMS)
        guild = self.bot.guilds[0] if self.bot.guilds else None
        return await self.game_serv.hydrate_user_names(guild=guild, rows=rows)

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
        entries = await self._fetch_game_leaderboard(game_type)
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
                used_count=len(state.get("used_words", [])),
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

    @commands.Cog.listener("on_message")
    async def game_answer_listener(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return

        if not isinstance(message.channel, discord.TextChannel):
            return

        content = message.content.strip()
        if not content:
            return

        game_type = TYPED_ANSWER_CHANNEL_MAP.get(message.channel.id)
        if game_type is None:
            return

        try:
            if game_type == "counting":
                await self._handle_counting_answer(message)
            elif game_type == "wordchain":
                await self._handle_wordchain_answer(message)
            elif game_type == "guess":
                await self._handle_guess_answer(message)
            elif game_type == "scramble":
                await self._handle_scramble_answer(message)

        except Exception:
            log.exception(
                "Game answer handler failed | game=%s channel=%s user=%s",
                game_type,
                message.channel.id,
                message.author.id,
            )

    async def _safe_react(self, message: discord.Message, emoji: str) -> None:
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            log.warning(
                "Failed to add reaction | message=%s emoji=%s",
                message.id,
                emoji,
            )

    async def _handle_counting_answer(self, message: discord.Message) -> None:
        raw = message.content.strip().replace(",", "")
        if not raw.lstrip("-").isdigit():
            return

        schedule_message_delete(message)

        state = await self.runtime.state("counting")
        if not state:
            return

        answer = int(state.get("answer", 0))

        if int(raw) != answer:
            await self._safe_react(message, "❌")
            return

        if not await self.games.try_claim_answer(
            game_type="counting",
            answer_key=answer,
        ):
            return

        reward = _counting_reward(str(state.get("question", "")))

        await self.game_serv.add_points(
            user_id=str(message.author.id),
            game_type="counting",
            score_points=reward,
            starlight_points=reward,
        )

        await self._safe_react(message, "✅")

        state = await self.runtime.reset_counting()

        await self.runtime.edit_game_panel(
            game_type="counting",
            embed=counting_embed(question=state["question"]),
            view=CountingGameView(),
        )

    async def _handle_wordchain_answer(self, message: discord.Message) -> None:
        word = _normalize_answer(message.content)
        if not word.isalpha() or len(word) < 2:
            return

        schedule_message_delete(message)

        state = await self.runtime.state("wordchain") or await self.runtime.reset_wordchain()
        current = str(state.get("word", ""))
        used = [str(w).lower() for w in state.get("used_words", [])]
        last_user_id = state.get("last_user_id")

        if str(message.author.id) == str(last_user_id):
            await self._safe_react(message, "❌")
            return

        if word in used or not word.startswith(current[-1].lower()):
            await self._safe_react(message, "❌")
            return

        used.append(word)

        state = {
            "word": word,
            "used_words": used[-500:],
            "last_user_id": str(message.author.id),
        }

        await self.games.upsert_state(
            game_type="wordchain",
            state=state,
        )

        await self.game_serv.add_points(
            user_id=str(message.author.id),
            game_type="wordchain",
            score_points=1,
            starlight_points=1,
        )

        await self._safe_react(message, "✅")

        await self.runtime.edit_game_panel(
            game_type="wordchain",
            embed=wordchain_embed(
                word=word,
                used_count=len(used),
            ),
            view=WordChainGameView(),
        )

    async def _handle_guess_answer(self, message: discord.Message) -> None:
        raw = message.content.strip().replace(",", "")
        if not raw.isdigit():
            return

        schedule_message_delete(message)

        state = await self.runtime.state("guess")
        if not state or not state.get("active", True):
            return

        submitted = int(raw)
        answer = int(state.get("answer", 0))

        if submitted < answer:
            await self._safe_react(message, "⬆️")
            return

        if submitted > answer:
            await self._safe_react(message, "⬇️")
            return

        if not await self.games.try_claim_answer(
            game_type="guess",
            answer_key=answer,
            extra_filter={"state.active": True},
        ):
            return

        await self.game_serv.add_points(
            user_id=str(message.author.id),
            game_type="guess",
            score_points=5,
            starlight_points=15,
        )

        await self._safe_react(message, "✅")

        state = await self.runtime.reset_guess()

        await self.runtime.edit_game_panel(
            game_type="guess",
            embed=guess_embed(active=bool(state.get("active", True))),
            view=GuessGameView(),
        )

    async def _handle_scramble_answer(self, message: discord.Message) -> None:
        state = await self.runtime.state("scramble")
        if not state:
            return

        schedule_message_delete(message)

        submitted = _normalize_answer(message.content)
        answer = _normalize_answer(str(state.get("answer", "")))

        if submitted != answer:
            await self._safe_react(message, "❌")
            return

        if not await self.games.try_claim_answer(
            game_type="scramble",
            answer_key=answer,
        ):
            return

        await self.game_serv.add_points(
            user_id=str(message.author.id),
            game_type="scramble",
            score_points=2,
            starlight_points=10,
        )

        await self._safe_react(message, "✅")

        state = await self.runtime.reset_scramble()

        await self.runtime.edit_game_panel(
            game_type="scramble",
            embed=scramble_embed(
                scrambled=state["scrambled"],
                hint_image_url=state.get("hint_image_url", ""),
            ),
            view=ScrambleGameView(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Game(bot))