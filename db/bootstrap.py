# db/bootstrap.py
from __future__ import annotations
import logging

from db.mongo import ping
from db.indexes import ensure_indexes
from db.seed import seed_items


log = logging.getLogger("db.bootstrap")


async def bootstrap_database() -> None:
    log.info("Starting database bootstrap")
    await ping()
    await ensure_indexes()
    await seed_items()
    log.info("Database bootstrap completed")
