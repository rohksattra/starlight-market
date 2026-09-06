"""Tenant-aware catalog seeding (items + monsters).

Runs on every bot start (deploy/redeploy). Missing rows are inserted.
Existing rows get catalog fields refreshed; identity and live prices stay put.
"""
from __future__ import annotations

import importlib.util
import logging
import uuid
from pathlib import Path
from typing import Any

from database.connection import get_db

log = logging.getLogger("database.seed")

GAMES_DIR = Path(__file__).resolve().parent.parent / "games"
SEED_ITEM_PRICE = 0


def _load_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load seed module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_game_catalog(game: str) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    seed_dir = GAMES_DIR / game / "seed"
    items_path = seed_dir / "items.py"
    monsters_path = seed_dir / "monsters.py"

    items: dict[str, list[dict[str, Any]]] = {}
    monsters: list[dict[str, Any]] = []

    if items_path.exists():
        mod = _load_module(items_path, f"starlight_seed_{game}_items")
        items = dict(getattr(mod, "DEFAULT_ITEMS", {}) or {})

    if monsters_path.exists():
        mod = _load_module(monsters_path, f"starlight_seed_{game}_monsters")
        monsters = list(getattr(mod, "DEFAULT_MONSTERS", []) or [])

    return items, monsters


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def item_catalog_fields(category: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_category": category,
        "item_image": item.get("item_image", "") or "",
        "item_emoji": item.get("item_emoji", "") or "🌟",
        "is_sell": _as_bool(item.get("is_sell"), True),
    }


def monster_catalog_fields(monster: dict[str, Any]) -> dict[str, Any]:
    return {
        "monster_level": _as_int(monster.get("monster_level"), 1),
        "monster_type": str(monster.get("monster_type") or "").strip(),
        "monster_health": _as_int(monster.get("monster_health"), 0),
        "monster_exp": _as_int(monster.get("monster_exp"), 0),
        "monster_gold": _as_int(monster.get("monster_gold"), 0),
        "monster_drop": str(monster.get("monster_drop") or ""),
        "monster_drop_note": str(monster.get("monster_drop_note") or ""),
        "monster_image": monster.get("monster_image", "") or "",
        "monster_emoji": str(monster.get("monster_emoji") or ""),
    }


def catalog_fields_match(existing: dict[str, Any], fields: dict[str, Any]) -> bool:
    """True when stored catalog fields already equal the seed payload."""
    for key, wanted in fields.items():
        current = existing.get(key, _MISSING)
        if key == "is_sell":
            left = _as_bool(True if current is _MISSING else current, True)
            if left != _as_bool(wanted, True):
                return False
            continue
        if key in {"monster_level", "monster_health", "monster_exp", "monster_gold"}:
            default = 1 if key == "monster_level" else 0
            left = _as_int(default if current is _MISSING else current, default)
            if left != _as_int(wanted, default):
                return False
            continue
        left = "" if current is _MISSING or current is None else str(current)
        right = "" if wanted is None else str(wanted)
        if left != right:
            return False
    return True


_MISSING = object()
_ITEM_COMPARE_PROJ = {
    "_id": 0,
    "item_name": 1,
    "item_category": 1,
    "item_image": 1,
    "item_emoji": 1,
    "is_sell": 1,
}
_MONSTER_COMPARE_PROJ = {
    "_id": 0,
    "monster_name": 1,
    "monster_level": 1,
    "monster_type": 1,
    "monster_health": 1,
    "monster_exp": 1,
    "monster_gold": 1,
    "monster_drop": 1,
    "monster_drop_note": 1,
    "monster_image": 1,
    "monster_emoji": 1,
}


async def seed_items(db_name: str, items: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """Insert missing items; refresh category/image/emoji. Never touch name or price."""
    if not items:
        return {"inserted": 0, "updated": 0}

    db = get_db(db_name)
    existing = {
        str(doc.get("item_name") or ""): doc
        for doc in await db.items.find({}, _ITEM_COMPARE_PROJ).to_list(None)
        if doc.get("item_name")
    }
    inserted = 0
    updated = 0
    for category, rows in items.items():
        for item in rows:
            name = item["item_name"]
            fields = item_catalog_fields(category, item)
            current = existing.get(name)
            if current is not None and catalog_fields_match(current, fields):
                continue
            result = await db.items.update_one(
                {"item_name": name},
                {
                    "$setOnInsert": {
                        "item_id": str(uuid.uuid4()),
                        "item_name": name,
                        "item_price": SEED_ITEM_PRICE,
                        "item_sold": 0,
                    },
                    "$set": fields,
                },
                upsert=True,
            )
            if result.upserted_id is not None:
                inserted += 1
            elif result.modified_count:
                updated += 1
    return {"inserted": inserted, "updated": updated}


async def seed_monsters(db_name: str, monsters: list[dict[str, Any]]) -> dict[str, int]:
    """Insert missing monsters; refresh level/health/image. Never touch name."""
    if not monsters:
        return {"inserted": 0, "updated": 0}

    db = get_db(db_name)
    existing = {
        str(doc.get("monster_name") or ""): doc
        for doc in await db.monsters.find({}, _MONSTER_COMPARE_PROJ).to_list(None)
        if doc.get("monster_name")
    }
    inserted = 0
    updated = 0
    for monster in monsters:
        name = monster["monster_name"]
        fields = monster_catalog_fields(monster)
        current = existing.get(name)
        if current is not None and catalog_fields_match(current, fields):
            continue
        result = await db.monsters.update_one(
            {"monster_name": name},
            {
                "$setOnInsert": {
                    "monster_id": str(uuid.uuid4()),
                    "monster_name": name,
                },
                "$set": fields,
            },
            upsert=True,
        )
        if result.upserted_id is not None:
            inserted += 1
        elif result.modified_count:
            updated += 1

    await db.monsters.update_many(
        {"monster_health": {"$exists": False}},
        {"$set": {"monster_health": 0}},
    )
    return {"inserted": inserted, "updated": updated}


async def seed_game(game: str, db_name: str) -> dict[str, int]:
    items, monsters = load_game_catalog(game)
    if not items and not monsters:
        log.warning("No seed catalog found | game=%s (fill games/%s/seed/)", game, game)
        return {
            "items_inserted": 0,
            "items_updated": 0,
            "monsters_inserted": 0,
            "monsters_updated": 0,
        }

    items_n = await seed_items(db_name, items)
    monsters_n = await seed_monsters(db_name, monsters)
    log.info(
        "Seed complete | game=%s db=%s items_new=%s items_updated=%s "
        "monsters_new=%s monsters_updated=%s",
        game,
        db_name,
        items_n["inserted"],
        items_n["updated"],
        monsters_n["inserted"],
        monsters_n["updated"],
    )
    return {
        "items_inserted": items_n["inserted"],
        "items_updated": items_n["updated"],
        "monsters_inserted": monsters_n["inserted"],
        "monsters_updated": monsters_n["updated"],
    }
