"""Game panel and typed-answer message handlers."""
from __future__ import annotations

import logging
import re
from typing import Any

import discord
from discord.ext import commands

from bot.activity_log import schedule_game_answer
from core.tenant import GameContext, get_context
from models.games import (
    TYPED_ANSWER_GAME_TYPES,
    GameType,
    PlayableGameType,
    TypedAnswerGameType,
)
from utils.scheduled_message_delete import schedule_message_delete


log = logging.getLogger("bot.handlers.games")

CHANNEL_ATTR: dict[PlayableGameType, str] = {
    "counting": "counting",
    "wordchain": "word_chain",
    "scramble": "scramble_word",
    "monster": "monster_hunt",
    "boss": "boss_battle",
}


def channel_id_for_game(ctx: GameContext, game_type: PlayableGameType) -> int:
    return int(getattr(ctx.channels, CHANNEL_ATTR[game_type], 0) or 0)


def typed_answer_channel_map(ctx: GameContext) -> dict[int, TypedAnswerGameType]:
    mapping: dict[int, TypedAnswerGameType] = {}
    for game_type in TYPED_ANSWER_GAME_TYPES:
        channel_id = channel_id_for_game(ctx, game_type)
        if channel_id:
            mapping[channel_id] = game_type
    return mapping


def _normalize_answer(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _counting_reward(question: str) -> int:
    if "*" in question or "/" in question:
        return 5
    return 2


class GameHandler:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._runtime = None

    @property
    def runtime(self):
        if self._runtime is None:
            from bot.games.runtime import GameRuntimeService

            self._runtime = GameRuntimeService(self.bot)
        return self._runtime

    async def fetch_game_leaderboard(
        self,
        guild: discord.Guild,
        ctx: GameContext,
        game_type: GameType,
    ) -> list[dict[str, Any]]:
        from bot.ui.games import MAX_ITEMS

        rows = await self.runtime.game_serv(ctx).fetch_leaderboard(
            game_type=game_type,
            limit=MAX_ITEMS,
        )
        for row in rows:
            name = "Unknown"
            member = guild.get_member(int(row["id"]))
            if member:
                name = member.display_name
            row["name"] = name
        return rows

    async def send_leaderboard_panel(
        self,
        *,
        channel: discord.TextChannel,
        ctx: GameContext,
        game_type: GameType,
    ) -> discord.Message:
        from bot.ui.games import (
            PAGE_SIZE,
            GameLeaderboardPaginationView,
            game_leaderboard_embed,
        )

        entries = await self.fetch_game_leaderboard(channel.guild, ctx, game_type)
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
        await self.runtime.games(ctx).upsert_panel(
            panel_type="leaderboard",
            game_type=game_type,
            channel_id=str(channel.id),
            message_id=str(message.id),
        )
        return message

    async def send_game_panel(
        self,
        *,
        channel: discord.TextChannel,
        ctx: GameContext,
        game_type: PlayableGameType,
    ) -> discord.Message:
        from bot.ui.games import (
            BattleGameView,
            CountingGameView,
            ScrambleGameView,
            WordChainGameView,
            battle_embed,
            counting_embed,
            scramble_embed,
            wordchain_embed,
        )

        runtime = self.runtime

        if game_type == "counting":
            state = await runtime.state(ctx, "counting") or await runtime.reset_counting(ctx)
            embed = counting_embed(question=str(state["question"]))
            view: discord.ui.View = CountingGameView()

        elif game_type == "wordchain":
            state = await runtime.state(ctx, "wordchain") or await runtime.reset_wordchain(ctx)
            embed = wordchain_embed(
                word=str(state["word"]),
                used_count=int(
                    state.get("used_count", len(state.get("used_words", []))) or 0
                ),
            )
            view = WordChainGameView()

        elif game_type == "scramble":
            state = await runtime.state(ctx, "scramble") or await runtime.reset_scramble(ctx)
            embed = scramble_embed(
                scrambled=str(state["scrambled"]),
                hint_image_url=str(state.get("hint_image_url", "")),
            )
            view = ScrambleGameView()

        elif game_type in {"monster", "boss"}:
            state = (
                await runtime.state(ctx, game_type)
                or await runtime.reset_enemy(ctx, game_type=game_type)
            )
            embed = battle_embed(game_type=game_type, state=state)
            view = BattleGameView(game_type=game_type)

        else:
            raise ValueError("Unknown game type")

        message = await channel.send(embed=embed, view=view)
        await runtime.games(ctx).upsert_panel(
            panel_type="game",
            game_type=game_type,
            channel_id=str(channel.id),
            message_id=str(message.id),
        )
        return message


class GameMessageHandler:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.game = get_game_handler(bot)

    @property
    def runtime(self):
        return self.game.runtime

    async def handle_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        if not message.content.strip():
            return

        ctx = get_context(message.guild.id)
        if ctx is None:
            return

        game_type = typed_answer_channel_map(ctx).get(message.channel.id)
        if game_type is None:
            return

        try:
            if game_type == "counting":
                await self._handle_counting_answer(message, ctx)
            elif game_type == "wordchain":
                await self._handle_wordchain_answer(message, ctx)
            elif game_type == "scramble":
                await self._handle_scramble_answer(message, ctx)
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
            log.warning("Failed to add reaction | message=%s emoji=%s", message.id, emoji)

    async def _handle_counting_answer(
        self,
        message: discord.Message,
        ctx: GameContext,
    ) -> None:
        from bot.ui.games import CountingGameView, counting_embed

        raw = message.content.strip().replace(",", "")
        if not raw.lstrip("-").isdigit():
            return

        schedule_game_answer(
            message=message,
            ctx=ctx,
            game_type="counting",
            answer=raw,
        )
        schedule_message_delete(message)

        state = await self.runtime.state(ctx, "counting")
        if not state:
            return

        answer = int(state.get("answer", 0))
        if int(raw) != answer:
            await self._safe_react(message, "❌")
            return

        if not await self.runtime.games(ctx).try_claim_answer(
            game_type="counting",
            answer_key=answer,
        ):
            return

        reward = _counting_reward(str(state.get("question", "")))
        await self.runtime.game_serv(ctx).add_points(
            user_id=str(message.author.id),
            game_type="counting",
            score_points=reward,
            starlight_points=reward,
        )
        await self._safe_react(message, "✅")

        state = await self.runtime.reset_counting(ctx)
        await self.runtime.edit_game_panel(
            ctx,
            game_type="counting",
            embed=counting_embed(question=state["question"]),
            view=CountingGameView(),
        )

    async def _handle_wordchain_answer(
        self,
        message: discord.Message,
        ctx: GameContext,
    ) -> None:
        from bot.ui.games import WordChainGameView, wordchain_embed

        word = _normalize_answer(message.content)
        if not word.isalpha() or len(word) < 2:
            return

        schedule_game_answer(
            message=message,
            ctx=ctx,
            game_type="wordchain",
            answer=word,
        )
        schedule_message_delete(message)

        state = await self.runtime.state(ctx, "wordchain") or await self.runtime.reset_wordchain(ctx)
        current = str(state.get("word", ""))
        used = [str(w).lower() for w in state.get("used_words", [])]
        used_count = int(state.get("used_count", len(used)) or len(used))
        last_user_id = state.get("last_user_id")

        if str(message.author.id) == str(last_user_id):
            await self._safe_react(message, "❌")
            return

        if word in used or not word.startswith(current[-1].lower()):
            await self._safe_react(message, "❌")
            return

        used.append(word)
        used_count += 1
        state = {
            "word": word,
            "used_words": used,
            "used_count": used_count,
            "last_user_id": str(message.author.id),
        }

        await self.runtime.games(ctx).upsert_state(game_type="wordchain", state=state)
        await self.runtime.game_serv(ctx).add_points(
            user_id=str(message.author.id),
            game_type="wordchain",
            score_points=1,
            starlight_points=1,
        )
        await self._safe_react(message, "✅")

        await self.runtime.edit_game_panel(
            ctx,
            game_type="wordchain",
            embed=wordchain_embed(word=word, used_count=used_count),
            view=WordChainGameView(),
        )

    async def _handle_scramble_answer(
        self,
        message: discord.Message,
        ctx: GameContext,
    ) -> None:
        from bot.ui.games import ScrambleGameView, scramble_embed

        state = await self.runtime.state(ctx, "scramble")
        if not state:
            return

        schedule_message_delete(message)

        submitted = _normalize_answer(message.content)
        answer = _normalize_answer(str(state.get("answer", "")))

        schedule_game_answer(
            message=message,
            ctx=ctx,
            game_type="scramble",
            answer=submitted,
        )

        if submitted != answer:
            await self._safe_react(message, "❌")
            return

        if not await self.runtime.games(ctx).try_claim_answer(
            game_type="scramble",
            answer_key=answer,
        ):
            return

        await self.runtime.game_serv(ctx).add_points(
            user_id=str(message.author.id),
            game_type="scramble",
            score_points=2,
            starlight_points=10,
        )
        await self._safe_react(message, "✅")

        state = await self.runtime.reset_scramble(ctx)
        await self.runtime.edit_game_panel(
            ctx,
            game_type="scramble",
            embed=scramble_embed(
                scrambled=state["scrambled"],
                hint_image_url=state.get("hint_image_url", ""),
            ),
            view=ScrambleGameView(),
        )


_game_handlers: dict[int, GameHandler] = {}
_message_handlers: dict[int, GameMessageHandler] = {}


def get_game_handler(bot: commands.Bot) -> GameHandler:
    key = id(bot)
    if key not in _game_handlers:
        _game_handlers[key] = GameHandler(bot)
    return _game_handlers[key]


def get_game_message_handler(bot: commands.Bot) -> GameMessageHandler:
    key = id(bot)
    if key not in _message_handlers:
        _message_handlers[key] = GameMessageHandler(bot)
    return _message_handlers[key]
