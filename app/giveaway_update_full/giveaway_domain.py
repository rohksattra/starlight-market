from __future__ import annotations

from datetime import datetime
from typing import Literal, TypedDict, cast


GiveawayStatus = Literal["open", "ended", "completed", "closed", "cancelled"]


class GiveawayInsert(TypedDict):
    giveaway_id: str
    guild_id: int
    channel_id: int
    host_user_id: str
    winner_count: int
    prize_description: str
    status: GiveawayStatus
    ends_at: datetime


class Giveaway(GiveawayInsert, total=False):
    message_id: int
    participant_user_ids: list[str]

    pending_winner_user_ids: list[str]
    winner_user_ids: list[str]
    claimed_winner_user_ids: list[str]

    updated_at: datetime

    announcement_channel_id: int
    announcement_message_id: int | None

    reroll_count: int
    last_rerolled_by: str
    last_rerolled_at: datetime

    closed_by: str
    closed_at: datetime

    cancelled_by: str
    cancelled_at: datetime


class GiveawayIdProjection(TypedDict):
    giveaway_id: str


class GiveawayScheduleProjection(TypedDict):
    giveaway_id: str
    ends_at: datetime


def giveaway_effective_status(doc: Giveaway) -> GiveawayStatus:
    raw = doc.get("status", "open")
    if raw in ("open", "ended", "completed", "closed", "cancelled"):
        return cast(GiveawayStatus, raw)
    return "open"