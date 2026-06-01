from __future__ import annotations

import logging
import uuid

from db.mongo import get_db
from utils.default_data import DEFAULT_ITEMS, DEFAULT_MONSTERS


log = logging.getLogger("db.seed")


async def seed_items() -> None:
    db = get_db()

    if not DEFAULT_ITEMS:
        return

    for category, items in DEFAULT_ITEMS.items():
        for item in items:
            await db.items.update_one(
                {
                    "item_category": category,
                    "item_name": item["item_name"],
                },
                {
                    "$set": {
                        "item_image": item["item_image"],
                        "item_emoji": item["item_emoji"],
                    },
                    "$setOnInsert": {
                        "item_id": str(uuid.uuid4()),
                        "item_category": category,
                        "item_name": item["item_name"],
                        "item_price": item["item_price"],
                    },
                },
                upsert=True,
            )

    log.info("Default items seeded/updated")


async def seed_monsters() -> None:
    db = get_db()

    if not DEFAULT_MONSTERS:
        return

    for monster in DEFAULT_MONSTERS:
        await db.monsters.update_one(
            {
                "monster_name": monster["monster_name"],
            },
            {
                "$set": {
                    "monster_level": monster["monster_level"],
                    "monster_image": monster["monster_image"],
                },
                "$setOnInsert": {
                    "monster_id": str(uuid.uuid4()),
                    "monster_name": monster["monster_name"],
                },
            },
            upsert=True,
        )

    log.info("Default monsters seeded/updated")