"""In-memory item/monster catalogs, keyed by tenant database name."""
from __future__ import annotations

import asyncio
from typing import Any

from database.items import ItemRepo
from database.monsters import MonsterRepo

_items: dict[str, list[dict[str, Any]]] = {}
_item_maps: dict[str, dict[str, dict[str, Any]]] = {}
_monsters: dict[str, list[dict[str, Any]]] = {}
_item_locks: dict[str, asyncio.Lock] = {}
_monster_locks: dict[str, asyncio.Lock] = {}


def invalidate_items(db_name: str) -> None:
    _items.pop(db_name, None)
    _item_maps.pop(db_name, None)


def invalidate_monsters(db_name: str) -> None:
    _monsters.pop(db_name, None)


def invalidate(db_name: str) -> None:
    invalidate_items(db_name)
    invalidate_monsters(db_name)


def clear() -> None:
    _items.clear()
    _item_maps.clear()
    _monsters.clear()


def _lock(store: dict[str, asyncio.Lock], db_name: str) -> asyncio.Lock:
    lock = store.get(db_name)
    if lock is None:
        lock = asyncio.Lock()
        store[db_name] = lock
    return lock


def _item_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": item.get("item_id"),
        "item_name": item.get("item_name", "Unknown Item"),
        "item_price": int(item.get("item_price", 0) or 0),
        "item_emoji": item.get("item_emoji") or "🌟",
        "item_category": item.get("item_category"),
        "item_image": item.get("item_image") or "",
    }


def _monster_view(monster: dict[str, Any]) -> dict[str, Any]:
    return {
        "monster_name": str(monster.get("monster_name") or "").strip(),
        "monster_level": int(monster.get("monster_level") or 1),
        "monster_type": str(monster.get("monster_type") or "").strip(),
        "monster_health": int(monster.get("monster_health") or 0),
        "monster_image": str(monster.get("monster_image") or ""),
        "monster_emoji": str(monster.get("monster_emoji") or ""),
    }


async def items(db_name: str) -> list[dict[str, Any]]:
    cached = _items.get(db_name)
    if cached is not None:
        return cached
    async with _lock(_item_locks, db_name):
        cached = _items.get(db_name)
        if cached is not None:
            return cached
        rows = [_item_view(item) for item in await ItemRepo(db_name).get_all()]
        _items[db_name] = rows
        _item_maps[db_name] = {
            str(item["item_id"]): item for item in rows if item.get("item_id")
        }
        return rows


async def item_map(db_name: str) -> dict[str, dict[str, Any]]:
    await items(db_name)
    return _item_maps.get(db_name, {})


async def monsters(db_name: str) -> list[dict[str, Any]]:
    cached = _monsters.get(db_name)
    if cached is not None:
        return cached
    async with _lock(_monster_locks, db_name):
        cached = _monsters.get(db_name)
        if cached is not None:
            return cached
        rows = [_monster_view(row) for row in await MonsterRepo(db_name).get_all()]
        _monsters[db_name] = rows
        return rows


def emoji_by_name(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(item.get("item_name") or "").casefold(): item.get("item_emoji") or "🌟"
        for item in rows
        if item.get("item_name")
    }


def emoji_by_id(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(item.get("item_id")): item.get("item_emoji") or "🌟"
        for item in rows
        if item.get("item_id")
    }


def filter_items(
    rows: list[dict[str, Any]],
    query: str,
    *,
    limit: int = 25,
    category: str | None = None,
) -> list[dict[str, Any]]:
    needle = query.strip().casefold()
    wanted = (category or "").strip()
    matched: list[dict[str, Any]] = []
    for item in rows:
        if wanted and str(item.get("item_category") or "") != wanted:
            continue
        name = str(item.get("item_name") or "")
        if needle and needle not in name.casefold():
            continue
        matched.append(item)
        if len(matched) >= limit:
            break
    return matched
