"""Tenant-aware game panel runtime (state, battles, panel edits)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import discord

from core.tenant import GameContext
from database.games import GameRepo
from models.games import (
    BATTLE_AUTO_NEW_ENEMY_SECONDS,
    BATTLE_GAME_TYPES,
    GameType,
    PlayableGameType,
)
from services.games import GameService


log = logging.getLogger("bot.games.runtime")


class GameRuntimeService:
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        self._services: dict[str, GameService] = {}
        self._repos: dict[str, GameRepo] = {}
        self._battle_auto_reset_tasks: dict[
            tuple[str, PlayableGameType],
            asyncio.Task[None] | None,
        ] = {}

    def game_serv(self, ctx: GameContext) -> GameService:
        cached = self._services.get(ctx.db_name)
        if cached is None:
            cached = GameService(ctx)
            self._services[ctx.db_name] = cached
        return cached

    def games(self, ctx: GameContext) -> GameRepo:
        cached = self._repos.get(ctx.db_name)
        if cached is None:
            cached = GameRepo(ctx.db_name)
            self._repos[ctx.db_name] = cached
        return cached

    async def state(
        self,
        ctx: GameContext,
        game_type: GameType,
    ) -> dict[str, Any] | None:
        doc = await self.games(ctx).get_state(game_type=game_type)
        if not doc:
            return None
        state = doc.get("state")
        return state if isinstance(state, dict) else None

    async def edit_game_panel(
        self,
        ctx: GameContext,
        *,
        game_type: PlayableGameType,
        embed: discord.Embed,
        view: discord.ui.View | None,
    ) -> None:
        panel = await self.games(ctx).get_panel(panel_type="game", game_type=game_type)
        if not panel:
            return

        channel = self.bot.get_channel(int(panel["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(int(panel["message_id"]))
            await message.edit(embed=embed, view=view)
        except discord.HTTPException:
            log.warning(
                "Game panel edit failed | game=%s db=%s",
                game_type,
                ctx.db_name,
            )

    async def reset_counting(self, ctx: GameContext) -> dict[str, Any]:
        question, answer = self.game_serv(ctx).counting_question()
        state = {"question": question, "answer": answer}
        await self.games(ctx).upsert_state(game_type="counting", state=state)
        return state

    async def reset_wordchain(self, ctx: GameContext) -> dict[str, Any]:
        word = self.game_serv(ctx).wordchain_seed()
        state = {
            "word": word,
            "used_words": [word],
            "used_count": 1,
            "last_user_id": None,
        }
        await self.games(ctx).upsert_state(game_type="wordchain", state=state)
        return state

    async def reset_scramble(self, ctx: GameContext) -> dict[str, Any]:
        state = await self.game_serv(ctx).scramble_word()
        await self.games(ctx).upsert_state(game_type="scramble", state=state)
        return state

    async def reset_enemy(
        self,
        ctx: GameContext,
        *,
        game_type: PlayableGameType,
    ) -> dict[str, Any]:
        serv = self.game_serv(ctx)
        state = await serv.battle_state(game_type)
        await self.games(ctx).upsert_state(game_type=game_type, state=state)
        return state

    def _battle_task_key(
        self,
        ctx: GameContext,
        game_type: PlayableGameType,
    ) -> tuple[str, PlayableGameType]:
        return (ctx.db_name, game_type)

    async def cancel_battle_auto_reset(
        self,
        ctx: GameContext,
        game_type: PlayableGameType,
    ) -> None:
        if game_type not in BATTLE_GAME_TYPES:
            return

        key = self._battle_task_key(ctx, game_type)
        current = asyncio.current_task()
        task = self._battle_auto_reset_tasks.get(key)

        if task is not None and not task.done() and task is not current:
            task.cancel()

        self._battle_auto_reset_tasks[key] = None

    async def start_battle_new_enemy(
        self,
        ctx: GameContext,
        game_type: PlayableGameType,
        *,
        cancel_existing: bool = True,
    ) -> dict[str, Any]:
        from bot.ui.games import BattleGameView, battle_embed

        if game_type not in BATTLE_GAME_TYPES:
            raise ValueError("Invalid battle game type")

        key = self._battle_task_key(ctx, game_type)
        if cancel_existing:
            await self.cancel_battle_auto_reset(ctx, game_type)
        else:
            self._battle_auto_reset_tasks[key] = None

        state = await self.reset_enemy(ctx, game_type=game_type)
        await self.edit_game_panel(
            ctx,
            game_type=game_type,
            embed=battle_embed(game_type=game_type, state=state, ctx=ctx),
            view=BattleGameView(game_type=game_type),
        )
        return state

    async def schedule_battle_auto_new_enemy(
        self,
        ctx: GameContext,
        *,
        game_type: PlayableGameType,
        delay_seconds: int,
    ) -> None:
        if game_type not in BATTLE_GAME_TYPES:
            return

        await self.cancel_battle_auto_reset(ctx, game_type)
        key = self._battle_task_key(ctx, game_type)

        async def _worker() -> None:
            try:
                await asyncio.sleep(max(0, delay_seconds))
                await self.start_battle_new_enemy(
                    ctx,
                    game_type,
                    cancel_existing=False,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception(
                    "Battle auto new enemy failed | game=%s db=%s",
                    game_type,
                    ctx.db_name,
                )

        self._battle_auto_reset_tasks[key] = asyncio.create_task(_worker())

    async def recover_battle_auto_reset(
        self,
        ctx: GameContext,
        game_type: PlayableGameType,
    ) -> None:
        if game_type not in BATTLE_GAME_TYPES:
            return

        state = await self.state(ctx, game_type)
        if not state:
            return

        hp = int(state.get("hp", 0) or 0)
        if hp > 0 and state.get("alive", True):
            return

        delay_seconds = BATTLE_AUTO_NEW_ENEMY_SECONDS[game_type]
        auto_new_enemy_at = state.get("auto_new_enemy_at")

        if not isinstance(auto_new_enemy_at, str):
            await self.schedule_battle_auto_new_enemy(
                ctx,
                game_type=game_type,
                delay_seconds=delay_seconds,
            )
            return

        try:
            spawn_dt = datetime.fromisoformat(auto_new_enemy_at)
            if spawn_dt.tzinfo is None:
                spawn_dt = spawn_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            await self.schedule_battle_auto_new_enemy(
                ctx,
                game_type=game_type,
                delay_seconds=delay_seconds,
            )
            return

        remaining = (spawn_dt - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            await self.start_battle_new_enemy(ctx, game_type)
            return

        await self.schedule_battle_auto_new_enemy(
            ctx,
            game_type=game_type,
            delay_seconds=int(remaining),
        )

    async def attack_enemy(
        self,
        ctx: GameContext,
        *,
        game_type: PlayableGameType,
        user_id: str,
    ) -> dict[str, Any]:
        from bot.ui.games import BattleGameView, battle_embed

        state = await self.state(ctx, game_type)
        if not state:
            state = await self.reset_enemy(ctx, game_type=game_type)
            await self.edit_game_panel(
                ctx,
                game_type=game_type,
                embed=battle_embed(game_type=game_type, state=state, ctx=ctx),
                view=BattleGameView(game_type=game_type),
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

            await self.edit_game_panel(
                ctx,
                game_type=game_type,
                embed=battle_embed(game_type=game_type, state=state, ctx=ctx),
                view=BattleGameView(game_type=game_type),
            )
            return {
                "state": state,
                "message": (
                    "❌ This enemy has been defeated. "
                    f"A new enemy will appear automatically {wait}."
                ),
            }

        serv = self.game_serv(ctx)
        max_hp = int(state.get("max_hp", hp) or hp)
        damage, is_crit = serv.roll_attack(max_hp=max_hp, game_type=game_type)
        dealt = min(damage, hp)
        sp, kill_bonus = serv.attack_rewards(
            dealt=dealt,
            max_hp=max_hp,
            game_type=game_type,
        )
        killed = dealt >= hp
        spawn_at_iso: str | None = None

        if killed and game_type in BATTLE_AUTO_NEW_ENEMY_SECONDS:
            delay = BATTLE_AUTO_NEW_ENEMY_SECONDS[game_type]
            spawn_at_iso = (
                datetime.now(timezone.utc) + timedelta(seconds=delay)
            ).isoformat()

        new_state = await self.games(ctx).try_apply_battle_hit(
            game_type=game_type,
            user_id=user_id,
            dealt=dealt,
            killed=killed,
            spawn_at_iso=spawn_at_iso,
        )

        if new_state is None:
            fresh = await self.state(ctx, game_type) or state
            hp_now = int(fresh.get("hp", 0) or 0)

            await self.edit_game_panel(
                ctx,
                game_type=game_type,
                embed=battle_embed(game_type=game_type, state=fresh, ctx=ctx),
                view=BattleGameView(game_type=game_type),
            )

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
                "state": fresh,
                "message": "❌ Attack failed due to conflict. Please try again.",
            }

        hit = "💥 Critical! You dealt" if is_crit else "⚔️ You dealt"
        message = (
            f"{hit} **{dealt:,} damage** "
            f"and gained **{sp} {ctx.brand.points_short}**."
        )

        await self.game_serv(ctx).add_points(
            user_id=user_id,
            game_type=game_type,
            score_points=dealt,
            market_points=sp,
        )

        if killed:
            await self.game_serv(ctx).add_points(
                user_id=user_id,
                game_type=game_type,
                score_points=0,
                market_points=kill_bonus,
            )
            message += f"\n🏆 Last hit bonus: **{kill_bonus} {ctx.brand.points_short}**."

            if game_type in BATTLE_AUTO_NEW_ENEMY_SECONDS:
                delay = BATTLE_AUTO_NEW_ENEMY_SECONDS[game_type]
                wait = (
                    f"**{delay // 60} minute(s)**"
                    if delay >= 60
                    else f"**{delay} seconds**"
                )
                message += f"\n🏁 New enemy automatically in {wait}."
                await self.schedule_battle_auto_new_enemy(
                    ctx,
                    game_type=game_type,
                    delay_seconds=delay,
                )

        await self.edit_game_panel(
            ctx,
            game_type=game_type,
            embed=battle_embed(game_type=game_type, state=new_state, ctx=ctx),
            view=BattleGameView(game_type=game_type),
        )

        return {
            "state": new_state,
            "message": message,
        }
