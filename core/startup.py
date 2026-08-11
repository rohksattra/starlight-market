"""
Run once at bot startup.
Ensures Mongo indexes exist for every game database.
"""
from __future__ import annotations

import logging

from bson.int64 import Int64

from core.tenant import all_contexts
from database.connection import get_db, ping
from database.indexes import ensure_indexes

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


async def warn_if_catalog_empty(db_name: str) -> None:
    """Warn when a tenant DB has no items (orders/scramble will fail)."""
    db = get_db(db_name)
    item_count = await db.items.count_documents({})
    if item_count == 0:
        log.warning(
            "Catalog empty | db=%s has 0 items — seed or migrate before taking orders",
            db_name,
        )
    else:
        log.info("Catalog ready | db=%s items=%s", db_name, item_count)


async def bootstrap() -> None:
    log.info("Bootstrap started")
    await ping()

    for ctx in all_contexts():
        await ensure_indexes(ctx.db_name)
        await ensure_order_number_counter(ctx.db_name)
        await warn_if_catalog_empty(ctx.db_name)
        log.info("Indexes ready | db=%s", ctx.db_name)

    log.info("Bootstrap complete")
