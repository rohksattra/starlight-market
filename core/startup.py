"""Startup bootstrap: Mongo ping, indexes, catalog seed, and counters."""
from __future__ import annotations

import logging

from bson.int64 import Int64

from core.tenant import all_contexts
from database.connection import get_db, ping
from database.indexes import ensure_indexes
from database.seed import seed_game

log = logging.getLogger("core.startup")


async def ensure_order_number_counter(db_name: str) -> None:
    db = get_db(db_name)
    last_order = await db.orders.find_one(
        {},
        sort=[("order_number", -1)],
        projection={"order_number": 1},
    )
    last_number = int(last_order["order_number"]) if last_order else 0
    await db.counters.update_one(
        {"_id": "order_number"},
        {"$max": {"value": Int64(last_number)}},
        upsert=True,
    )
    log.info("Order counter initialized | db=%s last=%s", db_name, last_number)


async def log_catalog_status(db_name: str) -> None:
    db = get_db(db_name)
    item_count = await db.items.count_documents({})
    monster_count = await db.monsters.count_documents({})
    if item_count == 0:
        log.warning("Catalog empty after seed | db=%s items=0 monsters=%s", db_name, monster_count)
    else:
        log.info(
            "Catalog ready | db=%s items=%s monsters=%s",
            db_name,
            item_count,
            monster_count,
        )


async def bootstrap() -> None:
    log.info("Bootstrap started")
    await ping()

    for ctx in all_contexts():
        await ensure_indexes(ctx.db_name)
        await ensure_order_number_counter(ctx.db_name)
        result = await seed_game(ctx.game, ctx.db_name)
        log.info(
            "Catalog seed checked | game=%s db=%s items_new=%s monsters_new=%s",
            ctx.game,
            ctx.db_name,
            result["items_inserted"],
            result["monsters_inserted"],
        )
        await log_catalog_status(ctx.db_name)
        log.info("Tenant bootstrap ready | game=%s db=%s", ctx.game, ctx.db_name)

    log.info("Bootstrap complete")
