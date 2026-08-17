"""Service for staff: cleanup data and delete-message validation."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Dict

from core.tenant import GameContext
from core.time import utc_now
from database.donations import DonationRepo
from database.orders import OrderRepo
from database.transaction_docs import TransactionRepo
from database.worker_ratings import WorkerRatingRepo
from models.enums import OrderStatus

log = logging.getLogger("services.staff")

CLEANUP_DAYS = 365
DISCORD_BULK_DELETE_LIMIT = 100


class CleanupdataService:
    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self.orders = OrderRepo(ctx.db_name)
        self.transactions = TransactionRepo(ctx.db_name)
        self.ratings = WorkerRatingRepo(ctx.db_name)
        self.donations = DonationRepo(ctx.db_name)

    async def cleanupdata(self) -> Dict[str, int]:
        cutoff = utc_now() - timedelta(days=CLEANUP_DAYS)
        result = {
            "orders_deleted": await self.orders.delete_by_status_updated_before(
                statuses=[OrderStatus.CLOSED, OrderStatus.CANCELED],
                cutoff=cutoff,
            ),
            "transactions_deleted": await self.transactions.delete_created_before(cutoff),
            "ratings_deleted": await self.ratings.delete_older_than(cutoff),
            "donations_deleted": await self.donations.delete_created_before(cutoff),
        }
        log.info(
            "Cleanupdata done | game=%s orders=%s tx=%s ratings=%s donations=%s",
            self.ctx.game,
            result["orders_deleted"],
            result["transactions_deleted"],
            result["ratings_deleted"],
            result["donations_deleted"],
        )
        return result


def validate_delete_quantity(quantity: int) -> None:
    if quantity <= 0 or quantity > DISCORD_BULK_DELETE_LIMIT:
        raise ValueError(f"Quantity must be between 1 and {DISCORD_BULK_DELETE_LIMIT}")
