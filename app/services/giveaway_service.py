from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import List
from uuid import uuid4

from app.domains.giveaway_domain import Giveaway, giveaway_effective_status
from app.repositories.giveaway_repo import GiveawayRepository


_finalize_locks: dict[str, asyncio.Lock] = {}


def finalize_lock(giveaway_id: str) -> asyncio.Lock:
    if giveaway_id not in _finalize_locks:
        _finalize_locks[giveaway_id] = asyncio.Lock()
    return _finalize_locks[giveaway_id]


class GiveawayService:
    def __init__(self) -> None:
        self.repo = GiveawayRepository()

    def new_giveaway_id(self) -> str:
        return uuid4().hex

    async def get_by_id(self, giveaway_id: str) -> Giveaway | None:
        return await self.repo.get_by_id(giveaway_id)

    async def require_giveaway(self, giveaway_id: str) -> Giveaway:
        doc = await self.repo.get_by_id(giveaway_id)
        if not doc:
            raise ValueError("Giveaway not found.")
        return doc

    async def join(
        self,
        *,
        giveaway_id: str,
        user_id: str,
        now: datetime,
    ) -> bool:
        doc = await self.require_giveaway(giveaway_id)

        host_id = str(doc.get("host_user_id", ""))
        if host_id == user_id:
            raise ValueError("You cannot join your own giveaway.")

        if giveaway_effective_status(doc) != "open":
            raise ValueError("This giveaway is no longer accepting entries.")

        if doc.get("ends_at") and doc["ends_at"] <= now:
            raise ValueError("This giveaway has ended.")

        return await self.repo.add_participant(
            giveaway_id=giveaway_id,
            user_id=user_id,
            now=now,
        )

    async def require_open(self, giveaway_id: str) -> Giveaway:
        doc = await self.require_giveaway(giveaway_id)
        if giveaway_effective_status(doc) != "open":
            raise ValueError("Refresh is locked after the giveaway timer ends.")
        return doc

    async def cancel_open(
        self,
        *,
        giveaway_id: str,
        moderator_id: str,
        now: datetime,
    ) -> Giveaway:
        doc = await self.require_giveaway(giveaway_id)
        if giveaway_effective_status(doc) != "open":
            raise ValueError("Giveaway can only be cancelled while open.")

        ok = await self.repo.cancel_open(
            giveaway_id=giveaway_id,
            moderator_id=moderator_id,
            now=now,
        )
        if not ok:
            raise ValueError("Failed to cancel giveaway.")

        updated = await self.repo.get_by_id(giveaway_id)
        if not updated:
            raise ValueError("Giveaway not found.")
        return updated

    async def require_completed(self, giveaway_id: str) -> Giveaway:
        doc = await self.require_giveaway(giveaway_id)
        if giveaway_effective_status(doc) != "completed":
            raise ValueError("Only completed giveaways support this action.")
        return doc

    def unclaimed_winners(self, doc: Giveaway) -> List[str]:
        claimed = set(str(uid) for uid in doc.get("claimed_winner_user_ids") or [])
        return [
            uid for uid in list(doc.get("winner_user_ids") or [])
            if uid not in claimed
        ]

    async def reroll_all_unclaimed(
        self,
        *,
        giveaway_id: str,
        moderator_id: str,
        now: datetime,
    ) -> List[str]:
        doc = await self.require_completed(giveaway_id)

        participants: List[str] = list(doc.get("participant_user_ids") or [])
        current_winners: List[str] = list(doc.get("winner_user_ids") or [])
        claimed = set(str(uid) for uid in doc.get("claimed_winner_user_ids") or [])

        if not participants or not current_winners:
            raise ValueError("No participants available for reroll.")

        locked_winners = [uid for uid in current_winners if uid in claimed]
        reroll_slots = len(current_winners) - len(locked_winners)

        if reroll_slots <= 0:
            raise ValueError("All winners already claimed. Nothing can be rerolled.")

        eligible = [uid for uid in participants if uid not in current_winners]
        if len(eligible) < reroll_slots:
            raise ValueError("Not enough eligible participants to reroll.")

        replacements = random.sample(eligible, k=reroll_slots)
        replacement_iter = iter(replacements)
        winners = [
            uid if uid in claimed else next(replacement_iter)
            for uid in current_winners
        ]

        ok = await self.repo.update_winners(
            giveaway_id=giveaway_id,
            winner_user_ids=winners,
            moderator_id=moderator_id,
            now=now,
        )
        if not ok:
            raise ValueError("Failed to update winners.")
        return winners

    async def reroll_selected(
        self,
        *,
        giveaway_id: str,
        selected_winner_ids: List[str],
        moderator_id: str,
        now: datetime,
    ) -> List[str]:
        doc = await self.require_completed(giveaway_id)

        participants: List[str] = list(doc.get("participant_user_ids") or [])
        current_winners: List[str] = list(doc.get("winner_user_ids") or [])
        claimed = set(str(uid) for uid in doc.get("claimed_winner_user_ids") or [])

        selected = [
            uid for uid in selected_winner_ids
            if uid in current_winners and uid not in claimed
        ]
        if not selected:
            raise ValueError("Selected winner is no longer valid.")

        eligible = [uid for uid in participants if uid not in current_winners]
        if len(eligible) < len(selected):
            raise ValueError("Not enough eligible participants to replace selected winner(s).")

        replacements = random.sample(eligible, k=len(selected))
        replacement_map = dict(zip(selected, replacements))
        new_winners = [
            replacement_map.get(uid, uid)
            for uid in current_winners
        ]

        ok = await self.repo.update_winners(
            giveaway_id=giveaway_id,
            winner_user_ids=new_winners,
            moderator_id=moderator_id,
            now=now,
        )
        if not ok:
            raise ValueError("Failed to update winners.")
        return new_winners

    async def mark_winners_claimed(
        self,
        *,
        giveaway_id: str,
        selected_winner_ids: List[str],
        now: datetime,
    ) -> Giveaway:
        doc = await self.require_completed(giveaway_id)

        current_winners = set(str(uid) for uid in doc.get("winner_user_ids") or [])
        selected = [uid for uid in selected_winner_ids if uid in current_winners]
        if not selected:
            raise ValueError("Selected winner is no longer valid.")

        for uid in selected:
            await self.repo.mark_winner_claimed(
                giveaway_id=giveaway_id,
                winner_user_id=uid,
                now=now,
            )

        updated = await self.repo.get_by_id(giveaway_id)
        if not updated:
            raise ValueError("Giveaway not found.")
        return updated

    async def close_completed(
        self,
        *,
        giveaway_id: str,
        moderator_id: str,
        now: datetime,
    ) -> Giveaway:
        doc = await self.require_completed(giveaway_id)

        winners = set(str(uid) for uid in doc.get("winner_user_ids") or [])
        claimed = set(str(uid) for uid in doc.get("claimed_winner_user_ids") or [])

        if not winners:
            raise ValueError("No winners to close.")

        if not winners.issubset(claimed):
            raise ValueError("All winners must claim their reward before closing.")

        ok = await self.repo.close_completed(
            giveaway_id=giveaway_id,
            moderator_id=moderator_id,
            now=now,
        )
        if not ok:
            raise ValueError("Failed to close giveaway.")

        updated = await self.repo.get_by_id(giveaway_id)
        if not updated:
            raise ValueError("Giveaway not found.")
        return updated

    async def lock_if_past_end(self, *, giveaway_id: str, now: datetime) -> None:
        await self.repo.lock_if_past_end(giveaway_id=giveaway_id, now=now)

    async def resolve_pending_winners(self, *, giveaway_id: str, doc: Giveaway) -> List[str]:
        winners = list(doc.get("pending_winner_user_ids") or [])
        if winners:
            return winners

        pids: List[str] = list(doc.get("participant_user_ids") or [])
        k = min(int(doc.get("winner_count", 1)), len(pids))
        winners = random.sample(pids, k=k) if k > 0 else []

        await self.repo.save_pending_winners(
            giveaway_id=giveaway_id,
            winner_user_ids=winners,
        )
        return winners

    async def complete_from_ended(
        self,
        *,
        giveaway_id: str,
        winner_user_ids: List[str],
        announcement_channel_id: int,
        announcement_message_id: int,
    ) -> bool:
        return await self.repo.complete_from_ended(
            giveaway_id=giveaway_id,
            winner_user_ids=winner_user_ids,
            announcement_channel_id=announcement_channel_id,
            announcement_message_id=announcement_message_id,
        )

    async def find_open_or_ended(self):
        return await self.repo.find_open_or_ended()

    async def find_open_past_end(self, *, now: datetime):
        return await self.repo.find_open_past_end(now=now)

    async def find_open_future(self, *, now: datetime, limit: int = 200):
        return await self.repo.find_open_future(now=now, limit=limit)

    async def insert_giveaway(self, doc) -> None:
        await self.repo.insert_one(doc)

    async def set_status(self, *, giveaway_id: str, status: str) -> None:
        await self.repo.set_status(giveaway_id=giveaway_id, status=status)

    async def update_message_id(
        self,
        *,
        giveaway_id: str,
        channel_id: int,
        message_id: int,
    ) -> None:
        await self.repo.update_message_id(
            giveaway_id=giveaway_id,
            channel_id=channel_id,
            message_id=message_id,
        )
