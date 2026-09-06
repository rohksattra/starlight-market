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

log = logging.getLogger("services.coa_reminders")

WORLDS_URL = "https://cdn.curseofaros.com/game/worlds.json"
METEOR_REMINDER_MINUTE = 55
METEOR_GRACE_SECONDS = 30
METEOR_DURATION_MINUTES = 5
BOOST_POLL_SECONDS = 30


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


class BoostTracker:
    """Baseline on first snapshot so a restart does not re-ping active boosts."""

    def __init__(self) -> None:
        self._primed = False
        self._boosted: set[int] = set()

    def consume(self, worlds: list[CoAWorld]) -> list[CoAWorld]:
        current = {world.world_id for world in worlds if world.is_boosted and is_trackable_world(world)}
        if not self._primed:
            self._primed = True
            self._boosted = current
            return []
        new_ids = current - self._boosted
        self._boosted = current
        return [world for world in worlds if world.world_id in new_ids]
