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

    if not await _has_index(db.system_flags, keys=["key"]):
        await db.system_flags.create_index("key", unique=True)
    # ================= USERS =================
    if not await _has_index(db.users, keys=["user_id"]):
        await db.users.create_index("user_id", unique=True)

    if not await _has_index(db.users, keys=["total_customer_spent"]):
        await db.users.create_index([("total_customer_spent", -1)])

    if not await _has_index(db.users, keys=["total_worker_income"]):
        await db.users.create_index([("total_worker_income", -1)])

    if not await _has_index(db.users, keys=["counting_score"]):
        await db.users.create_index([("counting_score", -1)])

    if not await _has_index(db.users, keys=["starlight_points"]):
        await db.users.create_index([("starlight_points", -1)])

    for field in (
        "wordchain_score",
        "guess_score",
        "treasure_score",
        "boss_score",
        "reaction_score",
        "scramble_score",
        "daily_score",
        "monster_score",
    ):
        if not await _has_index(db.users, keys=[field]):
            await db.users.create_index([(field, -1)])
    # ================= GAMES =================
    if not await _has_index(db.game_panels, keys=["panel_type", "game_type"]):
        await db.game_panels.create_index([("panel_type", 1), ("game_type", 1)], unique=True)

    if not await _has_index(db.game_states, keys=["game_type"]):
        await db.game_states.create_index("game_type", unique=True)

    if not await _has_index(db.game_user_states, keys=["game_type", "user_id"]):
        await db.game_user_states.create_index([("game_type", 1), ("user_id", 1)], unique=True)
    # ================= MONSTERS =================
    if not await _has_index(db.monsters, keys=["monster_id"]):
        await db.monsters.create_index("monster_id", unique=True)

    if not await _has_index(db.monsters, keys=["monster_name"]):
        await db.monsters.create_index("monster_name", unique=True)

    if not await _has_index(db.monsters, keys=["monster_level"]):
        await db.monsters.create_index([("monster_level", 1)])
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
    # ================= GIVEAWAYS =================
    if not await _has_index(db.giveaways, keys=["giveaway_id"]):
        await db.giveaways.create_index("giveaway_id", unique=True)

    if not await _has_index(db.giveaways, keys=["message_id"]):
        await db.giveaways.create_index("message_id", unique=True, sparse=True)

    log.info("MongoDB indexes ensured (aligned with services & repositories)")