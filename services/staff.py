"""Service for staff: cleanup data and delete-message validation."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict

from core.tenant import GameContext
from database.connection import get_db
from models.enums import OrderStatus

log = logging.getLogger("services.staff")

CLEANUP_DAYS = 365
DISCORD_BULK_DELETE_LIMIT = 100


class CleanupdataService:
    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        db = get_db(ctx.db_name)
        self.orders = db.orders
        self.transactions = db.transactions
        self.ratings = db.worker_ratings

    async def cleanupdata(self) -> Dict[str, int]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=CLEANUP_DAYS)

        order_res = await self.orders.delete_many(
            {
                "order_status": {"$in": [OrderStatus.CLOSED, OrderStatus.CANCELED]},
                "updated_at": {"$lt": cutoff},
            }
        )
        tx_res = await self.transactions.delete_many(
            {
                "created_at": {"$lt": cutoff},
            }
        )
        rating_res = await self.ratings.delete_many(
            {
                "$or": [
                    {"rated_at": {"$lt": cutoff}},
                    {"expired_at": {"$lt": cutoff}},
                ],
            }
        )

        result = {
            "orders_deleted": order_res.deleted_count,
            "transactions_deleted": tx_res.deleted_count,
            "ratings_deleted": rating_res.deleted_count,
        }
        log.info(
            "Cleanupdata done | game=%s orders=%s tx=%s ratings=%s",
            self.ctx.game,
            result["orders_deleted"],
            result["transactions_deleted"],
            result["ratings_deleted"],
        )
        return result


def validate_delete_quantity(quantity: int) -> None:
    if quantity <= 0 or quantity > DISCORD_BULK_DELETE_LIMIT:
        raise ValueError(f"Quantity must be between 1 and {DISCORD_BULK_DELETE_LIMIT}")
