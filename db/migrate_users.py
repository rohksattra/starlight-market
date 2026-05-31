from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from bson.int64 import Int64

from db.indexes import ensure_indexes
from db.mongo import close_mongo, get_db, ping


log = logging.getLogger("db.migrate_users")


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def _upsert_user_from_customer(*, customer: dict) -> None:
    user_id = str(customer.get("customer_id", "")).strip()
    if not user_id:
        return

    now = datetime.utcnow()

    await get_db().users.update_one(
        {"user_id": user_id},
        {
            "$setOnInsert": {
                "user_id": user_id,
                "total_worker_finished_item": Int64(0),
                "total_worker_income": Int64(0),
                "count_worker_rating": Int64(0),
                "total_worker_star": Int64(0),
            },
            "$set": {
                "total_customer_order": Int64(
                    _safe_int(customer.get("total_customer_order", 0))
                ),
                "total_customer_spent": Int64(
                    _safe_int(customer.get("total_customer_spent", 0))
                ),
                "updated_at": now,
            },
        },
        upsert=True,
    )


async def _upsert_user_from_worker(*, worker: dict) -> None:
    user_id = str(worker.get("worker_id", "")).strip()
    if not user_id:
        return

    now = datetime.utcnow()

    await get_db().users.update_one(
        {"user_id": user_id},
        {
            "$setOnInsert": {
                "user_id": user_id,
                "total_customer_order": Int64(0),
                "total_customer_spent": Int64(0),
                "counting_score": Int64(0),
            },
            "$set": {
                "total_worker_finished_item": Int64(
                    _safe_int(worker.get("total_worker_finished_item", 0))
                ),
                "total_worker_income": Int64(
                    _safe_int(worker.get("total_worker_income", 0))
                ),
                "count_worker_rating": Int64(
                    _safe_int(worker.get("count_worker_rating", 0))
                ),
                "total_worker_star": Int64(
                    _safe_int(worker.get("total_worker_star", 0))
                ),
                "updated_at": now,
            },
        },
        upsert=True,
    )


async def migrate_users() -> None:
    log.info("Starting migration: customers/workers -> users")

    await ping()
    await ensure_indexes()

    db = get_db()

    migrated_customers = 0
    migrated_workers = 0

    async for c in db.customers.find({}, {"_id": 0}):
        await _upsert_user_from_customer(customer=c)
        migrated_customers += 1

    async for w in db.workers.find({}, {"_id": 0}):
        await _upsert_user_from_worker(worker=w)
        migrated_workers += 1

    log.info(
        "Migration completed: customers=%s workers=%s -> users",
        migrated_customers,
        migrated_workers,
    )


if __name__ == "__main__":
    try:
        asyncio.run(migrate_users())
    finally:
        asyncio.run(close_mongo())