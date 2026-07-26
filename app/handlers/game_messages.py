from __future__ import annotations

import logging
import re

import discord
from discord.ext import commands

from app.handlers.game import get_game_handler
from app.services.game_constants import TYPED_ANSWER_CHANNEL_MAP
from app.views.game_embed import counting_embed, guess_embed, scramble_embed, wordchain_embed
from app.views.game_view import CountingGameView, GuessGameView, ScrambleGameView, WordChainGameView
from utils.scheduled_message_delete import schedule_message_delete


log = logging.getLogger("handlers.game_messages")


def _normalize_answer(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _counting_reward(question: str) -> int:
    if "*" in question or "/" in question:
        return 5
    return 2


class GameMessageHandler:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.game = get_game_handler(bot)

    @property
    def runtime(self):
        return self.game.runtime

    @property
    def game_serv(self):
        return self.game.game_serv

    @property
    def games(self):
        return self.game.games

    async def handle_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        if not message.content.strip():
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
            log.warning("Failed to add reaction | message=%s emoji=%s", message.id, emoji)

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

        if not await self.games.try_claim_answer(game_type="counting", answer_key=answer):
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

        await self.games.upsert_state(game_type="wordchain", state=state)
        await self.game_serv.add_points(
            user_id=str(message.author.id),
            game_type="wordchain",
            score_points=1,
            starlight_points=1,
        )
        await self._safe_react(message, "✅")

        await self.runtime.edit_game_panel(
            game_type="wordchain",
            embed=wordchain_embed(word=word, used_count=used_count),
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

        if not await self.games.try_claim_answer(game_type="scramble", answer_key=answer):
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


_handlers: dict[int, GameMessageHandler] = {}


def get_game_message_handler(bot: commands.Bot) -> GameMessageHandler:
    key = id(bot)
    if key not in _handlers:
        _handlers[key] = GameMessageHandler(bot)
    return _handlers[key]
