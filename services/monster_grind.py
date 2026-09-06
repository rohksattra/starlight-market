"""Independent expected-value grind estimates from monster drop tables."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.tenant import GameContext
from database.monsters import MonsterRepo
from services import catalog_cache

FALLBACK_EMOJI = "🌟"
MAX_KILL_COUNT = 1_000_000
_EMPTY_DROP = frozenset({"", "none", "null", "-"})
_DROP_RE = re.compile(
    r"^(?P<name>.+?)\s+\(\s*(?:1/(?P<denom>[\d.]+)|None)\s*\)"
    r"(?:\s+\(\s*(?P<qty>None|\d+(?:\s*-\s*\d+)?)\s*\))?$",
    re.IGNORECASE,
)
_DROP_ROLLS_RE = re.compile(r"drops\s+(\d+)\s+items", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedDrop:
    name: str
    chance_denom: float
    qty_min: int
    qty_max: int


@dataclass(frozen=True)
class DropEstimate:
    name: str
    emoji: str
    chance_denom: float
    qty_min: int
    qty_max: int
    expected_min: float
    expected_max: float


@dataclass(frozen=True)
class GrindEstimate:
    monster_name: str
    monster_level: int
    monster_emoji: str
    monster_image: str
    monster_drop_note: str
    drop_rolls: int
    kill_count: int
    total_exp: int
    total_gold: int
    drops: list[DropEstimate]


def parse_monster_drops(raw: str) -> list[ParsedDrop]:
    text = (raw or "").strip()
    if text.casefold() in _EMPTY_DROP:
        return []

    parsed: list[ParsedDrop] = []
    for part in (chunk.strip() for chunk in text.split(",") if chunk.strip()):
        match = _DROP_RE.match(part)
        if match is None or match.group("denom") is None:
            continue
        denom = float(match.group("denom"))
        if denom <= 0:
            continue
        qty_min, qty_max = _parse_qty(match.group("qty"))
        parsed.append(
            ParsedDrop(
                name=match.group("name").strip(),
                chance_denom=denom,
                qty_min=qty_min,
                qty_max=qty_max,
            )
        )
    return parsed


def format_chance_denom(denom: float) -> str:
    if denom <= 0:
        return "?"
    if abs(denom - round(denom)) < 1e-9:
        return f"1/{int(round(denom))}"
    return f"1/{denom:.4f}".rstrip("0").rstrip(".")


def format_qty_range(lo: float, hi: float) -> str:
    if hi < 1:
        return "<1"
    high = f"{round(hi):,}"
    if lo < 1:
        return f"<1–{high}"
    low = f"{round(lo):,}"
    if low == high:
        return low
    return f"{low}–{high}"


def parse_drop_rolls(note: str) -> int:
    match = _DROP_ROLLS_RE.search(note or "")
    if match is None:
        return 1
    rolls = int(match.group(1))
    return rolls if rolls > 1 else 1


def estimate_drops(
    drops: list[ParsedDrop],
    kill_count: int,
    *,
    drop_rolls: int = 1,
) -> list[tuple[ParsedDrop, float, float]]:
    rolls = drop_rolls if drop_rolls > 1 else 1
    rows: list[tuple[ParsedDrop, float, float]] = []
    for drop in drops:
        hits = kill_count * rolls / drop.chance_denom
        rows.append((drop, hits * drop.qty_min, hits * drop.qty_max))
    rows.sort(key=lambda row: (row[0].chance_denom, row[0].name.casefold()))
    return rows


def _parse_qty(raw: str | None) -> tuple[int, int]:
    if raw is None or raw.casefold() == "none":
        return 1, 1
    if "-" in raw:
        left, right = raw.split("-", 1)
        return int(left), int(right)
    qty = int(raw)
    return qty, qty


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _emoji_or_star(value: Any) -> str:
    text = str(value or "").strip()
    return text or FALLBACK_EMOJI


class MonsterGrindService:
    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self.monsters = MonsterRepo(ctx.db_name)

    async def autocomplete(self, current: str) -> list[tuple[str, str]]:
        query = current.strip().casefold()
        choices: list[tuple[str, str]] = []
        for row in await catalog_cache.monsters(self.ctx.db_name):
            name = str(row.get("monster_name") or "").strip()
            if not name:
                continue
            if query and query not in name.casefold():
                continue
            level = _as_int(row.get("monster_level"), 1)
            label = f"{name} (Lv {level})"
            choices.append((label[:100], name))
            if len(choices) >= 25:
                break
        return choices

    async def estimate(self, *, monster_name: str, kill_count: int) -> GrindEstimate:
        if kill_count < 1 or kill_count > MAX_KILL_COUNT:
            raise ValueError(f"Kill count must be between 1 and {MAX_KILL_COUNT:,}.")

        monster = await self.monsters.get_by_name(monster_name)
        if monster is None:
            raise ValueError("Monster not found.")

        emoji_map = catalog_cache.emoji_by_name(await catalog_cache.items(self.ctx.db_name))
        parsed = parse_monster_drops(str(monster.get("monster_drop") or ""))
        note = str(monster.get("monster_drop_note") or "").strip()
        drop_rolls = parse_drop_rolls(note)
        drops = [
            DropEstimate(
                name=drop.name,
                emoji=emoji_map.get(drop.name.casefold(), FALLBACK_EMOJI),
                chance_denom=drop.chance_denom,
                qty_min=drop.qty_min,
                qty_max=drop.qty_max,
                expected_min=expected_min,
                expected_max=expected_max,
            )
            for drop, expected_min, expected_max in estimate_drops(
                parsed, kill_count, drop_rolls=drop_rolls
            )
        ]
        return GrindEstimate(
            monster_name=str(monster.get("monster_name") or monster_name),
            monster_level=_as_int(monster.get("monster_level"), 1),
            monster_emoji=_emoji_or_star(monster.get("monster_emoji")),
            monster_image=str(monster.get("monster_image") or ""),
            monster_drop_note=note,
            drop_rolls=drop_rolls,
            kill_count=kill_count,
            total_exp=_as_int(monster.get("monster_exp")) * kill_count,
            total_gold=_as_int(monster.get("monster_gold")) * kill_count,
            drops=drops,
        )
