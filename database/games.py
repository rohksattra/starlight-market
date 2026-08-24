"""Mongo queries for game panels and game states."""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.time import utc_now
from database.connection import get_db
from models.games import GamePanel, GamePanelType, GameStateDocument, GameType, PlayableGameType, TypedAnswerGameType


class GameRepo:
    def __init__(self, db_name: str) -> None:
        db = get_db(db_name)
        self.panels = db.game_panels
        self.states = db.game_states

    async def upsert_panel(
        self,
        *,
        panel_type: GamePanelType,
        game_type: GameType,
        channel_id: str,
        message_id: str,
    ) -> None:
        now = utc_now()
        await self.panels.update_one(
            {"panel_type": panel_type, "game_type": game_type},
            {
                "$set": {
                    "panel_type": panel_type,
                    "game_type": game_type,
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def get_panel(
        self,
        *,
        panel_type: GamePanelType,
        game_type: GameType,
    ) -> Optional[GamePanel]:
        return await self.panels.find_one(
            {"panel_type": panel_type, "game_type": game_type},
            {"_id": 0},
        )

    async def upsert_state(self, *, game_type: GameType, state: Dict[str, Any]) -> None:
        now = utc_now()
        await self.states.update_one(
            {"game_type": game_type},
            {
                "$set": {
                    "game_type": game_type,
                    "state": state,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def get_state(self, *, game_type: GameType) -> Optional[GameStateDocument]:
        return await self.states.find_one({"game_type": game_type}, {"_id": 0})

    async def update_state_fields(
        self,
        *,
        game_type: GameType,
        fields: Dict[str, Any],
    ) -> None:
        await self.states.update_one(
            {"game_type": game_type},
            {
                "$set": {
                    **{f"state.{k}": v for k, v in fields.items()},
                    "updated_at": utc_now(),
                }
            },
            upsert=True,
        )

    async def try_claim_answer(
        self,
        *,
        game_type: TypedAnswerGameType,
        answer_key: str | int,
        extra_filter: Dict[str, Any] | None = None,
    ) -> bool:
        filt: Dict[str, Any] = {
            "game_type": game_type,
            "state.answer": answer_key,
        }
        if extra_filter:
            filt.update(extra_filter)

        result = await self.states.update_one(
            filt,
            {
                "$set": {
                    "state.answer": None,
                    "updated_at": utc_now(),
                }
            },
        )
        return result.modified_count == 1

    async def try_apply_battle_hit(
        self,
        *,
        game_type: PlayableGameType,
        user_id: str,
        dealt: int,
        killed: bool,
        spawn_at_iso: str | None = None,
    ) -> Dict[str, Any] | None:
        for _ in range(5):
            doc = await self.get_state(game_type=game_type)
            if not doc:
                return None

            state = doc.get("state")
            if not isinstance(state, dict):
                return None

            hp = int(state.get("hp", 0) or 0)
            alive = bool(state.get("alive", True))
            if hp <= 0 or not alive:
                return None

            new_hp = max(0, hp - dealt)
            damage_map = dict(state.get("damage") or {})
            damage_map[user_id] = int(damage_map.get(user_id, 0)) + dealt

            new_state: Dict[str, Any] = {
                **state,
                "hp": new_hp,
                "damage": damage_map,
            }
            if killed:
                new_state["alive"] = False
                if spawn_at_iso:
                    new_state["auto_new_enemy_at"] = spawn_at_iso

            result = await self.states.update_one(
                {
                    "game_type": game_type,
                    "state.hp": hp,
                    "state.alive": alive,
                },
                {
                    "$set": {
                        "state": new_state,
                        "updated_at": utc_now(),
                    }
                },
            )
            if result.modified_count == 1:
                return new_state

        return None
