from __future__ import annotations

import logging

from bson.int64 import Int64

from db.indexes import ensure_indexes
from db.mongo import get_db, ping
from db.seed import seed_items, seed_monsters


log = logging.getLogger("db.bootstrap")


async def ensure_order_number_counter() -> None:
    db = get_db()

    last_order = await db.orders.find_one(
        {},
        sort=[("order_number", -1)],
        projection={"order_number": 1},
    )

    last_number = (
        int(last_order["order_number"])
        if last_order
        else 0
    )

    await db.counters.update_one(
        {"_id": "order_number"},
        {
            "$max": {
                "value": Int64(last_number),
            }
        },
        upsert=True,
    )

    log.info(
        "Order counter initialized | last_order=%s",
        last_number,
    )


async def bootstrap_database() -> None:
    log.info("Starting database bootstrap")

    await ping()
    await ensure_indexes()

    await ensure_order_number_counter()

    await seed_items()
    await seed_monsters()

    log.info("Database bootstrap completed")