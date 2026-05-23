from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from db.mongo import get_db
from app.domains.giveaway_domain import (
    Giveaway,
    GiveawayIdProjection,
    GiveawayInsert,
    GiveawayScheduleProjection,
    GiveawayStatus,
)


class GiveawayRepository:
    def __init__(self) -> None:
        self.col = get_db().giveaways

    async def insert_one(self, doc: GiveawayInsert) -> None:
        await self.col.insert_one(doc)

    async def get_by_id(self, giveaway_id: str) -> Optional[Giveaway]:
        return await self.col.find_one(
            {"giveaway_id": giveaway_id},
            {"_id": 0},
        )

    async def update_message_id(
        self,
        *,
        giveaway_id: str,
        channel_id: int,
        message_id: int,
    ) -> None:
        await self.col.update_one(
            {"giveaway_id": giveaway_id},
            {
                "$set": {
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

    async def add_participant(
        self,
        *,
        giveaway_id: str,
        user_id: str,
        now: datetime,
    ) -> bool:
        res = await self.col.update_one(
            {
                "giveaway_id": giveaway_id,
                "status": "open",
                "ends_at": {"$gt": now},
            },
            {
                "$addToSet": {
                    "participant_user_ids": user_id,
                },
                "$set": {
                    "updated_at": now,
                },
            },
        )

        return res.modified_count > 0

    async def set_status(
        self,
        *,
        giveaway_id: str,
        status: GiveawayStatus,
    ) -> None:
        await self.col.update_one(
            {"giveaway_id": giveaway_id},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

    async def save_pending_winners(
        self,
        *,
        giveaway_id: str,
        winner_user_ids: List[str],
    ) -> bool:
        res = await self.col.update_one(
            {
                "giveaway_id": giveaway_id,
                "status": "ended",
            },
            {
                "$set": {
                    "pending_winner_user_ids": winner_user_ids,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        return res.modified_count > 0

    async def complete_from_ended(
        self,
        *,
        giveaway_id: str,
        winner_user_ids: List[str],
        announcement_channel_id: int,
        announcement_message_id: int | None,
    ) -> bool:
        res = await self.col.update_one(
            {
                "giveaway_id": giveaway_id,
                "status": "ended",
            },
            {
                "$set": {
                    "status": "completed",
                    "winner_user_ids": winner_user_ids,
                    "claimed_winner_user_ids": [],
                    "announcement_channel_id": announcement_channel_id,
                    "announcement_message_id": announcement_message_id,
                    "reroll_count": 0,
                    "updated_at": datetime.utcnow(),
                },
                "$unset": {
                    "pending_winner_user_ids": "",
                },
            },
        )

        return res.modified_count > 0

    async def update_winners(
        self,
        *,
        giveaway_id: str,
        winner_user_ids: List[str],
        moderator_id: str,
        now: datetime,
    ) -> bool:
        res = await self.col.update_one(
            {
                "giveaway_id": giveaway_id,
                "status": "completed",
            },
            {
                "$set": {
                    "winner_user_ids": winner_user_ids,
                    "last_rerolled_by": moderator_id,
                    "last_rerolled_at": now,
                    "updated_at": now,
                },
                "$inc": {
                    "reroll_count": 1,
                },
            },
        )

        return res.modified_count > 0

    async def mark_winner_claimed(
        self,
        *,
        giveaway_id: str,
        winner_user_id: str,
        now: datetime,
    ) -> bool:
        res = await self.col.update_one(
            {
                "giveaway_id": giveaway_id,
                "status": "completed",
                "winner_user_ids": winner_user_id,
            },
            {
                "$addToSet": {
                    "claimed_winner_user_ids": winner_user_id,
                },
                "$set": {
                    "updated_at": now,
                },
            },
        )

        return res.modified_count > 0

    async def close_completed(
        self,
        *,
        giveaway_id: str,
        moderator_id: str,
        now: datetime,
    ) -> bool:
        res = await self.col.update_one(
            {
                "giveaway_id": giveaway_id,
                "status": "completed",
            },
            {
                "$set": {
                    "status": "closed",
                    "closed_by": moderator_id,
                    "closed_at": now,
                    "updated_at": now,
                }
            },
        )

        return res.modified_count > 0

    async def cancel_open(
        self,
        *,
        giveaway_id: str,
        moderator_id: str,
        now: datetime,
    ) -> bool:
        res = await self.col.update_one(
            {
                "giveaway_id": giveaway_id,
                "status": "open",
            },
            {
                "$set": {
                    "status": "cancelled",
                    "cancelled_by": moderator_id,
                    "cancelled_at": now,
                    "updated_at": now,
                }
            },
        )

        return res.modified_count > 0

    async def lock_if_past_end(
        self,
        *,
        giveaway_id: str,
        now: datetime,
    ) -> bool:
        res = await self.col.update_one(
            {
                "giveaway_id": giveaway_id,
                "status": "open",
                "ends_at": {"$lte": now},
            },
            {
                "$set": {
                    "status": "ended",
                    "updated_at": now,
                }
            },
        )

        return res.modified_count > 0

    async def find_open_or_ended(self) -> List[GiveawayIdProjection]:
        cursor = self.col.find(
            {
                "message_id": {"$ne": None},
                "status": {
                    "$in": [
                        "open",
                        "ended",
                        "completed",
                        "closed",
                        "cancelled",
                    ]
                },
            },
            {
                "_id": 0,
                "giveaway_id": 1,
            },
        ).limit(500)

        return [d async for d in cursor]

    async def find_open_past_end(
        self,
        *,
        now: datetime,
    ) -> List[Giveaway]:
        cursor = self.col.find(
            {
                "status": "open",
                "ends_at": {"$lte": now},
                "message_id": {"$ne": None},
            },
            {"_id": 0},
        )

        return [d async for d in cursor]

    async def find_open_future(
        self,
        *,
        now: datetime,
        limit: int = 200,
    ) -> List[GiveawayScheduleProjection]:
        cursor = self.col.find(
            {
                "status": "open",
                "message_id": {"$ne": None},
                "ends_at": {"$gt": now},
            },
            {
                "_id": 0,
                "giveaway_id": 1,
                "ends_at": 1,
            },
        ).limit(limit)

        return [d async for d in cursor]