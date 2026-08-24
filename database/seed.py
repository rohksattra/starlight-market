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


def item_catalog_fields(category: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_category": category,
        "item_image": item.get("item_image", "") or "",
        "item_emoji": item.get("item_emoji", "") or "🌟",
    }


def monster_catalog_fields(monster: dict[str, Any]) -> dict[str, Any]:
    return {
        "monster_level": _as_int(monster.get("monster_level"), 1),
        "monster_health": _as_int(monster.get("monster_health"), 0),
        "monster_image": monster.get("monster_image", "") or "",
    }


async def seed_items(db_name: str, items: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """Insert missing items; refresh category/image/emoji. Never touch name or price."""
    if not items:
        return {"inserted": 0, "updated": 0}

    db = get_db(db_name)
    inserted = 0
    updated = 0
    for category, rows in items.items():
        for item in rows:
            result = await db.items.update_one(
                {"item_name": item["item_name"]},
                {
                    "$setOnInsert": {
                        "item_id": str(uuid.uuid4()),
                        "item_name": item["item_name"],
                        "item_price": SEED_ITEM_PRICE,
                        "item_sold": 0,
                    },
                    "$set": item_catalog_fields(category, item),
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
    inserted = 0
    updated = 0
    for monster in monsters:
        result = await db.monsters.update_one(
            {"monster_name": monster["monster_name"]},
            {
                "$setOnInsert": {
                    "monster_id": str(uuid.uuid4()),
                    "monster_name": monster["monster_name"],
                },
                "$set": monster_catalog_fields(monster),
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
