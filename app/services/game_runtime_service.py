from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import discord

from app.domains.game_domain import GameType, PlayableGameType
from app.repositories.game_repo import GameRepository
from app.services.game_constants import (
    BATTLE_AUTO_NEW_ENEMY_SECONDS,
    BATTLE_GAME_TYPES,
    REACTION_AUTO_RESET_SECONDS,
)
from app.services.game_service import GameService
from app.uis.game_embed import battle_embed, reaction_embed
from app.uis.game_view import BattleGameView, ReactionRushGameView


log = logging.getLogger("services.game_runtime")


class GameRuntimeService:
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        self.game_serv = GameService()
        self.games = GameRepository()
        self._reaction_auto_reset_task: asyncio.Task[None] | None = None
        self._battle_auto_reset_tasks: dict[PlayableGameType, asyncio.Task[None] | None] = {
            "monster": None,
            "boss": None,
        }

    async def state(
        self,
        game_type: GameType,
    ) -> Dict[str, Any] | None:
        doc = await self.games.get_state(
            game_type=game_type,
        )

        if not doc:
            return None

        state = doc.get("state")
        return state if isinstance(state, dict) else None

    async def edit_game_panel(
        self,
        *,
        game_type: PlayableGameType,
        embed: discord.Embed,
        view: discord.ui.View | None,
    ) -> None:
        panel = await self.games.get_panel(
            panel_type="game",
            game_type=game_type,
        )

        if not panel:
            return

        channel = self.bot.get_channel(
            int(panel["channel_id"]),
        )

        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(
                int(panel["message_id"]),
            )

            await message.edit(
                embed=embed,
                view=view,
            )

        except discord.HTTPException:
            log.warning(
                "Game panel edit failed | game=%s",
                game_type,
            )

    async def reset_counting(self) -> Dict[str, Any]:
        question, answer = self.game_serv.counting_question()

        state = {
            "question": question,
            "answer": answer,
        }

        await self.games.upsert_state(
            game_type="counting",
            state=state,
        )

        return state

    async def reset_wordchain(self) -> Dict[str, Any]:
        word = self.game_serv.wordchain_seed()

        state = {
            "word": word,
            "used_words": [word],
            "last_user_id": None,
        }

        await self.games.upsert_state(
            game_type="wordchain",
            state=state,
        )

        return state

    async def reset_guess(self) -> Dict[str, Any]:
        state = {
            "answer": self.game_serv.guess_number(),
            "active": True,
        }

        await self.games.upsert_state(
            game_type="guess",
            state=state,
        )

        return state

    async def reset_scramble(self) -> Dict[str, Any]:
        state = self.game_serv.scramble_word()

        await self.games.upsert_state(
            game_type="scramble",
            state=state,
        )

        return state

    async def reset_reaction(self) -> Dict[str, Any]:
        state = self.game_serv.reaction_round()

        await self.games.upsert_state(
            game_type="reaction",
            state=state,
        )

        return state

    async def cancel_reaction_auto_reset(self) -> None:
        if self._reaction_auto_reset_task is not None and not self._reaction_auto_reset_task.done():
            self._reaction_auto_reset_task.cancel()

        self._reaction_auto_reset_task = None

    async def start_reaction_new_round(self) -> None:
        await self.cancel_reaction_auto_reset()
        await self.reset_reaction()

        await self.edit_game_panel(
            game_type="reaction",
            embed=reaction_embed(claimed_count=0),
            view=ReactionRushGameView(click_disabled=False),
        )

    async def schedule_reaction_auto_reset(
        self,
        *,
        delay_seconds: int,
    ) -> None:
        await self.cancel_reaction_auto_reset()

        async def _worker() -> None:
            try:
                await asyncio.sleep(
                    max(0, delay_seconds),
                )

                await self.start_reaction_new_round()

            except asyncio.CancelledError:
                raise

            except Exception:
                log.exception("Reaction rush auto-reset failed")

        self._reaction_auto_reset_task = asyncio.create_task(_worker())

    async def recover_reaction_auto_reset(self) -> None:
        state = await self.state("reaction")

        if not state:
            return

        claimed = list(
            state.get("claimed_user_ids") or []
        )

        if len(claimed) < 3:
            return

        auto_reset_at = state.get("auto_reset_at")

        if not isinstance(auto_reset_at, str):
            await self.schedule_reaction_auto_reset(
                delay_seconds=REACTION_AUTO_RESET_SECONDS,
            )
            return

        try:
            reset_dt = datetime.fromisoformat(auto_reset_at)

            if reset_dt.tzinfo is None:
                reset_dt = reset_dt.replace(
                    tzinfo=timezone.utc,
                )

        except ValueError:
            await self.schedule_reaction_auto_reset(
                delay_seconds=REACTION_AUTO_RESET_SECONDS,
            )
            return

        remaining = (
            reset_dt - datetime.now(timezone.utc)
        ).total_seconds()

        if remaining <= 0:
            await self.start_reaction_new_round()
            return

        await self.schedule_reaction_auto_reset(
            delay_seconds=int(remaining),
        )

    async def reset_enemy(
        self,
        *,
        game_type: PlayableGameType,
    ) -> Dict[str, Any]:
        state = (
            self.game_serv.boss_state()
            if game_type == "boss"
            else self.game_serv.monster_state()
        )

        await self.games.upsert_state(
            game_type=game_type,
            state=state,
        )

        return state

    async def cancel_battle_auto_reset(
        self,
        game_type: PlayableGameType,
    ) -> None:
        if game_type not in BATTLE_GAME_TYPES:
            return

        task = self._battle_auto_reset_tasks.get(game_type)

        if task is not None and not task.done():
            task.cancel()

        self._battle_auto_reset_tasks[game_type] = None

    async def start_battle_new_enemy(
        self,
        game_type: PlayableGameType,
    ) -> Dict[str, Any]:
        if game_type not in BATTLE_GAME_TYPES:
            raise ValueError("Invalid battle game type")

        await self.cancel_battle_auto_reset(game_type)

        state = await self.reset_enemy(
            game_type=game_type,
        )

        await self.edit_game_panel(
            game_type=game_type,
            embed=battle_embed(
                game_type=game_type,
                state=state,
            ),
            view=BattleGameView(game_type=game_type),
        )

        return state

    async def schedule_battle_auto_new_enemy(
        self,
        *,
        game_type: PlayableGameType,
        delay_seconds: int,
    ) -> None:
        if game_type not in BATTLE_GAME_TYPES:
            return

        await self.cancel_battle_auto_reset(game_type)

        async def _worker() -> None:
            try:
                await asyncio.sleep(
                    max(0, delay_seconds),
                )

                await self.start_battle_new_enemy(game_type)

            except asyncio.CancelledError:
                raise

            except Exception:
                log.exception(
                    "Battle auto new enemy failed | game=%s",
                    game_type,
                )

        self._battle_auto_reset_tasks[game_type] = asyncio.create_task(_worker())

    async def recover_battle_auto_reset(
        self,
        game_type: PlayableGameType,
    ) -> None:
        if game_type not in BATTLE_GAME_TYPES:
            return

        state = await self.state(game_type)

        if not state:
            return

        hp = int(state.get("hp", 0) or 0)

        if hp > 0 and state.get("alive", True):
            return

        delay_seconds = BATTLE_AUTO_NEW_ENEMY_SECONDS[game_type]
        auto_new_enemy_at = state.get("auto_new_enemy_at")

        if not isinstance(auto_new_enemy_at, str):
            await self.schedule_battle_auto_new_enemy(
                game_type=game_type,
                delay_seconds=delay_seconds,
            )
            return

        try:
            spawn_dt = datetime.fromisoformat(auto_new_enemy_at)

            if spawn_dt.tzinfo is None:
                spawn_dt = spawn_dt.replace(
                    tzinfo=timezone.utc,
                )

        except ValueError:
            await self.schedule_battle_auto_new_enemy(
                game_type=game_type,
                delay_seconds=delay_seconds,
            )
            return

        remaining = (
            spawn_dt - datetime.now(timezone.utc)
        ).total_seconds()

        if remaining <= 0:
            await self.start_battle_new_enemy(game_type)
            return

        await self.schedule_battle_auto_new_enemy(
            game_type=game_type,
            delay_seconds=int(remaining),
        )

    async def claim_treasure(
        self,
        *,
        user_id: str,
    ) -> Dict[str, Any]:
        reward = self.game_serv.treasure_reward()

        await self.game_serv.add_points(
            user_id=user_id,
            game_type="treasure",
            score_points=int(reward["score"]),
            starlight_points=int(reward["points"]),
        )

        return reward

    async def claim_reaction(
        self,
        *,
        user_id: str,
    ) -> Dict[str, Any]:
        if not await self.state("reaction"):
            await self.reset_reaction()

        claimed_result = await self.games.try_claim_reaction_slot(
            user_id=user_id,
        )

        if claimed_result is None:
            state = await self.state("reaction") or {}
            claimed = list(
                state.get("claimed_user_ids") or []
            )

            if user_id in claimed:
                raise ValueError("You already claimed this round")

            raise ValueError("This round is already full")

        rank, state = claimed_result
        rewards = list(
            state.get("rewards") or [20, 10, 5]
        )

        reward = int(rewards[rank - 1])

        if rank >= 3:
            reset_at = datetime.now(timezone.utc) + timedelta(
                seconds=REACTION_AUTO_RESET_SECONDS,
            )

            await self.games.update_state_fields(
                game_type="reaction",
                fields={
                    "auto_reset_at": reset_at.isoformat(),
                },
            )

        score_reward = {
            1: 3,
            2: 2,
            3: 1,
        }[rank]

        await self.game_serv.add_points(
            user_id=user_id,
            game_type="reaction",
            score_points=score_reward,
            starlight_points=reward,
        )

        if rank >= 3:
            await self.schedule_reaction_auto_reset(
                delay_seconds=REACTION_AUTO_RESET_SECONDS,
            )

        return {
            "rank": rank,
            "score": score_reward,
            "points": reward,
            "claimed_count": rank,
        }

    async def claim_daily(
        self,
        *,
        user_id: str,
    ) -> Dict[str, Any]:
        return await self.game_serv.claim_daily(
            user_id=user_id,
        )

    async def attack_enemy(
        self,
        *,
        game_type: PlayableGameType,
        user_id: str,
    ) -> Dict[str, Any]:
        state = await self.state(game_type)

        if not state:
            state = await self.reset_enemy(
                game_type=game_type,
            )

        hp = int(state.get("hp", 0) or 0)

        if hp <= 0 or not state.get("alive", True):
            wait = "soon"

            if game_type in BATTLE_AUTO_NEW_ENEMY_SECONDS:
                seconds = BATTLE_AUTO_NEW_ENEMY_SECONDS[game_type]
                wait = (
                    f"in **{seconds // 60} minute(s)**"
                    if seconds >= 60
                    else f"in **{seconds} seconds**"
                )

            return {
                "state": state,
                "message": (
                    "❌ This enemy has been defeated. "
                    f"A new enemy will appear automatically {wait}."
                ),
            }

        if game_type == "boss":
            damage = random.randint(300, 900)
            sp = max(1, damage // 75)
            kill_bonus = 100
        else:
            damage = random.randint(10, 150)
            sp = max(1, damage // 30)
            kill_bonus = 25

        dealt = min(damage, hp)
        killed = dealt >= hp
        spawn_at_iso: str | None = None

        if killed and game_type in BATTLE_AUTO_NEW_ENEMY_SECONDS:
            delay = BATTLE_AUTO_NEW_ENEMY_SECONDS[game_type]
            spawn_at_iso = (
                datetime.now(timezone.utc)
                + timedelta(seconds=delay)
            ).isoformat()

        new_state = await self.games.try_apply_battle_hit(
            game_type=game_type,
            user_id=user_id,
            dealt=dealt,
            killed=killed,
            spawn_at_iso=spawn_at_iso,
        )

        if new_state is None:
            fresh = await self.state(game_type) or state
            hp_now = int(fresh.get("hp", 0) or 0)

            if hp_now <= 0 or not fresh.get("alive", True):
                wait = "soon"

                if game_type in BATTLE_AUTO_NEW_ENEMY_SECONDS:
                    seconds = BATTLE_AUTO_NEW_ENEMY_SECONDS[game_type]
                    wait = (
                        f"in **{seconds // 60} minute(s)**"
                        if seconds >= 60
                        else f"in **{seconds} seconds**"
                    )

                return {
                    "state": fresh,
                    "message": (
                        "❌ This enemy has been defeated. "
                        f"A new enemy will appear automatically {wait}."
                    ),
                }

            return {
                "state": state,
                "message": "❌ Attack failed due to conflict. Please try again.",
            }

        message = (
            f"⚔️ You dealt **{dealt:,} damage** "
            f"and gained **{sp} SP**."
        )

        await self.game_serv.add_points(
            user_id=user_id,
            game_type=game_type,
            score_points=dealt,
            starlight_points=sp,
        )

        if killed:
            await self.game_serv.add_points(
                user_id=user_id,
                game_type=game_type,
                score_points=0,
                starlight_points=kill_bonus,
            )

            message += f"\n🏆 Last hit bonus: **{kill_bonus} SP**."

            if game_type in BATTLE_AUTO_NEW_ENEMY_SECONDS:
                delay = BATTLE_AUTO_NEW_ENEMY_SECONDS[game_type]
                wait = (
                    f"**{delay // 60} minute(s)**"
                    if delay >= 60
                    else f"**{delay} seconds**"
                )

                message += f"\n🏁 New enemy automatically in {wait}."

                await self.schedule_battle_auto_new_enemy(
                    game_type=game_type,
                    delay_seconds=delay,
                )

        return {
            "state": new_state,
            "message": message,
        }