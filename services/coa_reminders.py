"""CoA meteor + world-boost reminder logic. No Discord imports."""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

from core.time import utc_now
from database.worlds import WorldRepo

log = logging.getLogger("services.coa_reminders")

WORLDS_URL = "https://cdn.curseofaros.com/game/worlds.json"
METEOR_REMINDER_MINUTE = 55
METEOR_GRACE_SECONDS = 30
METEOR_DURATION_MINUTES = 5
BOOST_POLL_SECONDS = 30
# Implied end vs stored end (countdown mismatch / shorter replacement).
SESSION_SLACK_MS = 120_000
# Remaining went up — a live boost never gets longer by itself.
REMAINING_INCREASE_MS = 30_000
END_GRACE_MS = 5_000


@dataclass(frozen=True)
class CoAWorld:
    world_id: int
    name: str
    region: str
    players: int
    is_boosted: bool
    boost_remaining: int
    members_only: bool


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def meteor_slot_key(when: datetime) -> str:
    return when.strftime("%Y%m%d%H")


def next_meteor_reminder_at(
    now: datetime,
    *,
    sent_slots: Iterable[str] = (),
) -> datetime:
    sent = set(sent_slots)
    candidate = now.replace(minute=METEOR_REMINDER_MINUTE, second=0, microsecond=0)
    if now > candidate + timedelta(seconds=METEOR_GRACE_SECONDS):
        candidate += timedelta(hours=1)
    while meteor_slot_key(candidate) in sent:
        candidate += timedelta(hours=1)
    return candidate


def meteor_event_window(reminder_at: datetime) -> tuple[datetime, datetime]:
    start = reminder_at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    end = start + timedelta(minutes=METEOR_DURATION_MINUTES)
    return start, end


def format_boost_remaining(boost_remaining_ms: int) -> str:
    remaining_ms = max(0, _as_int(boost_remaining_ms, 0))
    if remaining_ms <= 0:
        return ""
    total_minutes = remaining_ms // 60_000
    if total_minutes == 0:
        return "less than 1 minute"
    hours, minutes = divmod(total_minutes, 60)
    parts: list[str] = []
    if hours:
        parts.append("1 hour" if hours == 1 else f"{hours} hours")
    if minutes:
        parts.append("1 minute" if minutes == 1 else f"{minutes} minutes")
    return " ".join(parts)


def boost_end_at(now: datetime, boost_remaining_ms: int) -> datetime | None:
    remaining_ms = _as_int(boost_remaining_ms, 0)
    if remaining_ms <= 0:
        return None
    return now + timedelta(milliseconds=remaining_ms)


def is_trackable_world(world: CoAWorld) -> bool:
    if world.world_id >= 200:
        return False
    return "qa" not in world.name.lower()


def parse_worlds(payload: Any) -> list[CoAWorld]:
    if not isinstance(payload, list):
        return []
    worlds: list[CoAWorld] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        world_id = _as_int(row.get("id"), 0)
        name = str(row.get("name") or "").strip()
        if world_id <= 0 or not name:
            continue
        worlds.append(
            CoAWorld(
                world_id=world_id,
                name=name,
                region=str(row.get("region") or "").strip(),
                players=_as_int(row.get("players"), 0),
                is_boosted=bool(row.get("is_boosted")),
                boost_remaining=_as_int(row.get("boost_remaining"), 0),
                members_only=bool(row.get("members_only")),
            )
        )
    return worlds


def fetch_worlds_sync(*, url: str = WORLDS_URL, timeout: float = 10) -> list[CoAWorld]:
    request = urllib.request.Request(url, headers={"User-Agent": "StarlightMarket/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return parse_worlds(json.loads(raw))


async def fetch_worlds(*, url: str = WORLDS_URL, timeout: float = 10) -> list[CoAWorld]:
    try:
        return await asyncio.to_thread(fetch_worlds_sync, url=url, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        log.exception("Failed to fetch CoA worlds | url=%s", url)
        return []


@dataclass
class WorldRecord:
    world_id: int
    name: str
    region: str
    is_boosted: bool
    boost_remaining: int
    boost_ends_at: datetime | None
    seen_at: datetime
    last_notified_ends_at: datetime | None

    def to_doc(self) -> dict[str, Any]:
        return {
            "world_id": self.world_id,
            "name": self.name,
            "region": self.region,
            "is_boosted": self.is_boosted,
            "boost_remaining": self.boost_remaining,
            "boost_ends_at": self.boost_ends_at,
            "seen_at": self.seen_at,
            "last_notified_ends_at": self.last_notified_ends_at,
        }


def world_record_from_doc(doc: dict[str, Any]) -> WorldRecord | None:
    world_id = _as_int(doc.get("world_id"), 0)
    name = str(doc.get("name") or "").strip()
    if world_id <= 0 or not name:
        return None
    ends_at = doc.get("boost_ends_at")
    if ends_at is not None and not isinstance(ends_at, datetime):
        ends_at = None
    notified = doc.get("last_notified_ends_at")
    if notified is not None and not isinstance(notified, datetime):
        notified = None
    seen_at = doc.get("seen_at")
    if not isinstance(seen_at, datetime):
        seen_at = utc_now()
    return WorldRecord(
        world_id=world_id,
        name=name,
        region=str(doc.get("region") or "").strip(),
        is_boosted=bool(doc.get("is_boosted")),
        boost_remaining=_as_int(doc.get("boost_remaining"), 0),
        boost_ends_at=ends_at,
        seen_at=seen_at,
        last_notified_ends_at=notified,
    )


class BoostTracker:
    """Tracks CoA worlds in memory and emits Mongo upserts.

    Empty tracker: first API snapshot is a silent baseline (no pings).
    Hydrated from DB: first poll compares against stored ends_at.
    Worlds missing from a poll are kept; failed/empty fetches write nothing.
    """

    def __init__(self) -> None:
        self._primed = False
        self._records: dict[int, WorldRecord] = {}
        self._upserts: list[dict[str, Any]] = []

    def hydrate(self, docs: list[dict[str, Any]]) -> None:
        for doc in docs:
            record = world_record_from_doc(doc)
            if record is None:
                continue
            self._records[record.world_id] = record
        self._primed = bool(self._records)

    def drain_upserts(self) -> list[dict[str, Any]]:
        rows = self._upserts
        self._upserts = []
        return rows

    def consume(self, worlds: list[CoAWorld], *, now: datetime | None = None) -> list[CoAWorld]:
        self._upserts = []
        if not worlds:
            return []
        moment = now or utc_now()
        if not self._primed:
            self._primed = True
            for world in worlds:
                if not is_trackable_world(world):
                    continue
                record = self._record_from_world(world, moment, acknowledged=True)
                self._records[world.world_id] = record
                self._upserts.append(record.to_doc())
            return []

        new_boosts: list[CoAWorld] = []
        for world in worlds:
            if not is_trackable_world(world):
                continue
            previous = self._records.get(world.world_id)
            active = world.is_boosted and world.boost_remaining > 0
            if previous is None:
                record = self._record_from_world(world, moment, acknowledged=active)
                self._records[world.world_id] = record
                self._upserts.append(record.to_doc())
                if active:
                    new_boosts.append(world)
                continue
            if active and self._is_new_session(previous, world.boost_remaining, moment):
                record = self._record_from_world(world, moment, acknowledged=True)
                self._records[world.world_id] = record
                self._upserts.append(record.to_doc())
                new_boosts.append(world)
                continue
            self._refresh_existing(previous, world, moment, active=active)
        return new_boosts

    def _record_from_world(
        self,
        world: CoAWorld,
        now: datetime,
        *,
        acknowledged: bool,
    ) -> WorldRecord:
        active = world.is_boosted and world.boost_remaining > 0
        ends_at = boost_end_at(now, world.boost_remaining) if active else None
        return WorldRecord(
            world_id=world.world_id,
            name=world.name,
            region=world.region,
            is_boosted=active,
            boost_remaining=world.boost_remaining if active else 0,
            boost_ends_at=ends_at,
            seen_at=now,
            last_notified_ends_at=ends_at if acknowledged and active else None,
        )

    def _refresh_existing(
        self,
        previous: WorldRecord,
        world: CoAWorld,
        now: datetime,
        *,
        active: bool,
    ) -> None:
        remaining = world.boost_remaining if active else previous.boost_remaining
        identity_changed = previous.name != world.name or previous.region != world.region
        status_changed = previous.is_boosted != active
        record = WorldRecord(
            world_id=world.world_id,
            name=world.name,
            region=world.region,
            is_boosted=active,
            boost_remaining=remaining,
            boost_ends_at=previous.boost_ends_at,
            seen_at=now if active or status_changed or identity_changed else previous.seen_at,
            last_notified_ends_at=previous.last_notified_ends_at,
        )
        self._records[world.world_id] = record
        if active or status_changed or identity_changed:
            self._upserts.append(record.to_doc())

    def _is_new_session(self, previous: WorldRecord, remaining_ms: int, now: datetime) -> bool:
        if previous.boost_ends_at is None:
            return True
        if now >= previous.boost_ends_at + timedelta(milliseconds=END_GRACE_MS):
            return True
        if remaining_ms > previous.boost_remaining + REMAINING_INCREASE_MS:
            return True
        implied_end = boost_end_at(now, remaining_ms)
        if implied_end is None:
            return False
        delta_ms = abs(int((implied_end - previous.boost_ends_at).total_seconds() * 1000))
        return delta_ms > SESSION_SLACK_MS


class WorldBoostService:
    """Load/persist world boost sessions through WorldRepo."""

    def __init__(self, db_name: str) -> None:
        self.repo = WorldRepo(db_name)
        self.tracker = BoostTracker()

    async def start(self) -> None:
        self.tracker.hydrate(await self.repo.get_all())

    async def consume(
        self,
        worlds: list[CoAWorld],
        *,
        now: datetime | None = None,
    ) -> list[CoAWorld]:
        new_boosts = self.tracker.consume(worlds, now=now)
        await self.repo.upsert_many(self.tracker.drain_upserts())
        return new_boosts
