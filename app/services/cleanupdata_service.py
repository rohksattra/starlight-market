# app/services/cleanup_service.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict

from db.mongo import get_db
from app.domains.enums.order_status_enum import OrderStatus


CLEANUP_DAYS = 30


class CleanupdataService:
    def __init__(self) -> None:
        db = get_db()
        self.orders = db.orders
        self.transactions = db.transactions
        self.ratings = db.worker_ratings

    async def cleanupdata(self) -> Dict[str, int]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=CLEANUP_DAYS)
        order_res = await self.orders.delete_many({
            "order_status": {"$in": [OrderStatus.CLOSED, OrderStatus.CANCELLED]},
            "updated_at": {"$lt": cutoff},
        })
        tx_res = await self.transactions.delete_many({
            "created_at": {"$lt": cutoff},
        })
        rating_res = await self.ratings.delete_many({
            "$or": [
                {"rated_at": {"$lt": cutoff}},
                {"expired_at": {"$lt": cutoff}},
            ],
        })
        return {
            "orders_deleted": order_res.deleted_count,
            "transactions_deleted": tx_res.deleted_count,
            "ratings_deleted": rating_res.deleted_count,
        }
