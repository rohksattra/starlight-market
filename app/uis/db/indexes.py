# db/indexes.py
from __future__ import annotations

import logging
from typing import Iterable

from db.mongo import get_db


log = logging.getLogger("db.indexes")


async def _has_index(collection, *, keys: Iterable[str]) -> bool:
    wanted = set(keys)
    index_info = await collection.index_information()
    for idx in index_info.values():
        existing = {k for k, _ in idx.get("key", [])}
        if wanted.issubset(existing):
            return True
    return False


async def ensure_indexes() -> None:
    db = get_db()

    # ================= CUSTOMERS =================
    if not await _has_index(db.customers, keys=["customer_id"]):
        await db.customers.create_index("customer_id", unique=True)
    if not await _has_index(db.customers, keys=["total_customer_spent"]):
        await db.customers.create_index([("total_customer_spent", -1)])
    # ================= ITEMS =================
    if not await _has_index(db.items, keys=["item_id"]):
        await db.items.create_index("item_id", unique=True)

    if not await _has_index(db.items, keys=["item_category", "item_name"]):
        await db.items.create_index([("item_category", 1), ("item_name", 1)], unique=True)
    # ================= ORDERS =================
    if not await _has_index(db.orders, keys=["order_id"]):
        await db.orders.create_index("order_id", unique=True)
    if not await _has_index(db.orders, keys=["channel_id"]):
        await db.orders.create_index("channel_id", unique=True, sparse=True)
    if not await _has_index(db.orders, keys=["order_number"]):
        await db.orders.create_index([("order_number", -1)])
    if not await _has_index(db.orders, keys=["customer_id"]):
        await db.orders.create_index("customer_id")
    if not await _has_index(db.orders, keys=["order_status"]):
        await db.orders.create_index("order_status")
    if not await _has_index(db.orders, keys=["customer_id", "order_status"]):
        await db.orders.create_index([("customer_id", 1), ("order_status", 1)])
    if not await _has_index(db.orders, keys=["worker_claims"]):
        await db.orders.create_index("worker_claims")
    if not await _has_index(db.orders, keys=["item_id"]):
        await db.orders.create_index("item_id")
    # ================= TRANSACTIONS =================
    if not await _has_index(db.transactions, keys=["transaction_id"]):
        await db.transactions.create_index("transaction_id", unique=True)
    if not await _has_index(db.transactions, keys=["order_id"]):
        await db.transactions.create_index("order_id")
    if not await _has_index(db.transactions, keys=["user_id", "user_role"]):
        await db.transactions.create_index([("user_id", 1), ("user_role", 1)])
    # ================= WORKER RATINGS =================
    if not await _has_index(db.worker_ratings, keys=["transaction_id"]):
        await db.worker_ratings.create_index("transaction_id", unique=True)
    if not await _has_index(db.worker_ratings, keys=["worker_id"]):
        await db.worker_ratings.create_index("worker_id")
    if not await _has_index(db.worker_ratings, keys=["customer_id"]):
        await db.worker_ratings.create_index("customer_id")
    if not await _has_index(db.worker_ratings, keys=["expired_at"]):
        await db.worker_ratings.create_index("expired_at", expireAfterSeconds=0)
    # ================= WORKERS =================
    if not await _has_index(db.workers, keys=["worker_id"]):
        await db.workers.create_index("worker_id", unique=True)
    if not await _has_index(db.workers, keys=["total_worker_income"]):
        await db.workers.create_index([("total_worker_income", -1)])

    log.info("MongoDB indexes ensured (aligned with services & repositories)")
