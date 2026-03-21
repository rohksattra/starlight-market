#app/repositories/claimable_repo.py
from __future__ import annotations

from typing import List
from db.mongo import get_db
from app.domains.order_domain import Order
from app.domains.enums.order_status_enum import OrderStatus


class ClaimableRepository:
    def __init__(self) -> None:
        self.orders = get_db().orders

    async def get_claimable_orders(self) -> List[Order]:
        cursor = (
            self.orders.find(
                {
                    "order_claims.order_claimable": {"$gt": 0},
                    "order_status": {
                        "$in": [OrderStatus.NEW, OrderStatus.CLAIMED],
                    },
                },
                {"_id": 0},
            )
            .sort("order_number", 1)
        )

        return [doc async for doc in cursor]