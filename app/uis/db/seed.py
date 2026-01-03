# db/seed.py
from __future__ import annotations

import logging
import uuid
from utils.default_data import DEFAULT_ITEMS
from db.mongo import get_db


log = logging.getLogger("db.seed")


async def seed_items() -> None:
    db = get_db()

    if not DEFAULT_ITEMS:
        return
    for category, items in DEFAULT_ITEMS.items():
        for item in items:
            await db.items.update_one(
                {"item_category": category, "item_name": item["item_name"]},
                {"$setOnInsert": {
                        "item_id": str(uuid.uuid4()),
                        "item_category": category,
                        "item_name": item["item_name"],
                        "item_price": item["item_price"],
                    }},
                upsert=True,
            )
    log.info("Default items seeded")
