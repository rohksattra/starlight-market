from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from pymongo import ReturnDocument

from db.mongo import get_db
from app.domains.game_domain import (
    GamePanel,
    GamePanelType,
    GameStateDocument,
    GameType,
    GameUserState,
    PlayableGameType,
    TypedAnswerGameType,
)


GamePanelData = GamePanel
GameStateData = GameStateDocument
GameUserStateData = GameUserState


class GameRepository:
    def __init__(self) -> None:
        db = get_db()
        self.panels = db.game_panels
        self.states = db.game_states
        self.user_states = db.game_user_states

    async def upsert_panel(
        self,
        *,
        panel_type: GamePanelType,
        game_type: GameType,
        channel_id: str,
        message_id: str,
    ) -> None:
        now = datetime.utcnow()
        await self.panels.update_one(
            {
                "panel_type": panel_type,
                "game_type": game_type,
            },
            {
                "$set": {
                    "panel_type": panel_type,
                    "game_type": game_type,
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

    async def get_panel(
        self,
        *,
        panel_type: GamePanelType,
        game_type: GameType,
    ) -> Optional[GamePanelData]:
        return await self.panels.find_one(
            {
                "panel_type": panel_type,
                "game_type": game_type,
            },
            {"_id": 0},
        )

    async def get_panels_by_type(self, panel_type: GamePanelType) -> list[GamePanelData]:
        cursor = self.panels.find({"panel_type": panel_type}, {"_id": 0})
        return [doc async for doc in cursor]

    async def upsert_state(
        self,
        *,
        game_type: GameType,
        state: Dict[str, Any],
    ) -> None:
        now = datetime.utcnow()
        await self.states.update_one(
            {"game_type": game_type},
            {
                "$set": {
                    "game_type": game_type,
                    "state": state,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

    async def get_state(self, *, game_type: GameType) -> Optional[GameStateData]:
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
                    "updated_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )

    async def get_user_state(
        self,
        *,
        game_type: GameType,
        user_id: str,
    ) -> Optional[GameUserStateData]:
        return await self.user_states.find_one(
            {
                "game_type": game_type,
                "user_id": user_id,
            },
            {"_id": 0},
        )

    async def upsert_user_state(
        self,
        *,
        game_type: GameType,
        user_id: str,
        state: Dict[str, Any],
    ) -> None:
        now = datetime.utcnow()
        await self.user_states.update_one(
            {
                "game_type": game_type,
                "user_id": user_id,
            },
            {
                "$set": {
                    "game_type": game_type,
                    "user_id": user_id,
                    "state": state,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

    async def try_claim_reaction_slot(self, *, user_id: str) -> Tuple[int, Dict[str, Any]] | None:
        """Atomically claim a reaction slot. Returns (rank, state) or None if unavailable."""
        doc = await self.states.find_one_and_update(
            {
                "game_type": "reaction",
                "state.claimed_user_ids": {"$ne": user_id},
                "$expr": {
                    "$lt": [
                        {"$size": {"$ifNull": ["$state.claimed_user_ids", []]}},
                        3,
                    ]
                },
            },
            {
                "$push": {"state.claimed_user_ids": user_id},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=ReturnDocument.AFTER,
            projection={"state": 1, "_id": 0},
        )
        if not doc:
            return None
        state = doc.get("state")
        if not isinstance(state, dict):
            return None
        claimed = list(state.get("claimed_user_ids") or [])
        return len(claimed), state

    async def try_apply_battle_hit(
        self,
        *,
        game_type: PlayableGameType,
        user_id: str,
        dealt: int,
        killed: bool,
        spawn_at_iso: str | None = None,
    ) -> Dict[str, Any] | None:
        """Optimistic HP/damage update; returns new state or None on conflict."""
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
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
            if result.modified_count == 1:
                return new_state
        return None

    async def try_claim_answer(
        self,
        *,
        game_type: TypedAnswerGameType,
        answer_key: str | int,
        extra_filter: Dict[str, Any] | None = None,
    ) -> bool:
        """Atomically mark a typed-answer puzzle solved (one winner)."""
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
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count == 1
