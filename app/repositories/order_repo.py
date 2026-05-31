from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson.int64 import Int64
from pymongo import ReturnDocument

from db.mongo import get_db
from app.domains.enums.order_status_enum import OrderStatus
from app.domains.order_domain import Order, OrderCreate


OrderData = Order
Session = Any


class OrderRepository:
    def __init__(self) -> None:
        db = get_db()

        self.orders = db.orders
        self.counters = db.counters

    async def get_by_id(self, order_id: str) -> Optional[OrderData]:
        return await self.orders.find_one(
            {"order_id": order_id},
            {"_id": 0},
        )

    async def get_by_channel_id(self, channel_id: str) -> Optional[OrderData]:
        return await self.orders.find_one(
            {"channel_id": channel_id},
            {"_id": 0},
        )

    async def next_order_number(self) -> int:
        doc = await self.counters.find_one_and_update(
            {"_id": "order_number"},
            {
                "$inc": {
                    "value": Int64(1),
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        return int(doc["value"])

    async def count_active_by_worker(self, worker_id: str) -> int:
        return await self.orders.count_documents(
            {
                f"worker_claims.{worker_id}": {"$gt": 0},
                "order_status": {
                    "$in": [
                        OrderStatus.NEW,
                        OrderStatus.CLAIMED,
                    ]
                },
            }
        )

    async def count_active_by_customer(self, customer_id: str) -> int:
        return await self.orders.count_documents(
            {
                "customer_id": customer_id,
                "order_status": {
                    "$in": [
                        OrderStatus.NEW,
                        OrderStatus.CLAIMED,
                        OrderStatus.COMPLETED,
                    ]
                },
            }
        )

    async def count_by_status(self, status: OrderStatus) -> int:
        return await self.orders.count_documents(
            {"order_status": status}
        )

    async def count_by_statuses(self, statuses: List[OrderStatus]) -> int:
        return await self.orders.count_documents(
            {"order_status": {"$in": statuses}}
        )

    def _session_kw(self, session: Session | None) -> dict:
        return {} if session is None else {"session": session}

    async def create_order(self, order: OrderCreate, *, session: Session | None = None) -> None:
        now = datetime.utcnow()

        await self.orders.update_one(
            {"order_id": order["order_id"]},
            {
                "$setOnInsert": {
                    **order,
                    "order_number": Int64(order["order_number"]),
                    "item_price": Int64(order["item_price"]),
                    "item_quantity": Int64(order["item_quantity"]),
                    "order_claims": {
                        "order_delivered": Int64(order["order_claims"]["order_delivered"]),
                        "order_completed": Int64(order["order_claims"]["order_completed"]),
                        "order_claimed": Int64(order["order_claims"]["order_claimed"]),
                        "order_claimable": Int64(order["order_claims"]["order_claimable"]),
                    },
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
            **self._session_kw(session),
        )

    async def update_fields(
        self,
        order_id: str,
        fields: Dict[str, Any],
        *,
        session: Session | None = None,
    ) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {"order_id": order_id},
            {"$set": {**fields, "updated_at": datetime.utcnow()}},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
            **self._session_kw(session),
        )

    async def set_channel(
        self,
        order_id: str,
        channel_id: str,
    ) -> None:
        await self.orders.update_one(
            {"order_id": order_id},
            {
                "$set": {
                    "channel_id": channel_id,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

    async def set_embed_message(
        self,
        order_id: str,
        message_id: str,
    ) -> None:
        await self.orders.update_one(
            {"order_id": order_id},
            {
                "$set": {
                    "embed_message_id": message_id,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

    async def get_active_by_worker(
        self,
        worker_id: str,
    ) -> List[OrderData]:
        cursor = self.orders.find(
            {
                f"worker_claims.{worker_id}": {"$gt": 0},
                "order_status": {
                    "$in": [
                        OrderStatus.NEW,
                        OrderStatus.CLAIMED,
                    ]
                },
            },
            {"_id": 0},
        )

        return [doc async for doc in cursor]

    async def get_active_by_customer(
        self,
        customer_id: str,
    ) -> List[OrderData]:
        cursor = self.orders.find(
            {
                "customer_id": customer_id,
                "order_status": {
                    "$in": [
                        OrderStatus.NEW,
                        OrderStatus.CLAIMED,
                        OrderStatus.COMPLETED,
                    ]
                },
            },
            {"_id": 0},
        )

        return [doc async for doc in cursor]

    async def inc_claim(
        self,
        *,
        order_id: str,
        worker_id: str,
        qty: int,
    ) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {
                "order_id": order_id,
                "order_status": {
                    "$in": [
                        OrderStatus.NEW,
                        OrderStatus.CLAIMED,
                    ]
                },
                "order_claims.order_claimable": {"$gte": qty},
            },
            {
                "$inc": {
                    f"worker_claims.{worker_id}": Int64(qty),
                    "order_claims.order_claimed": Int64(qty),
                    "order_claims.order_claimable": Int64(-qty),
                },
                "$set": {
                    "order_status": OrderStatus.CLAIMED,
                    "updated_at": datetime.utcnow(),
                },
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def inc_unclaim(
        self,
        *,
        order_id: str,
        worker_id: str,
        qty: int,
    ) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {
                "order_id": order_id,
                f"worker_claims.{worker_id}": {"$gte": qty},
                "order_status": {
                    "$in": [
                        OrderStatus.NEW,
                        OrderStatus.CLAIMED,
                    ]
                },
            },
            {
                "$inc": {
                    f"worker_claims.{worker_id}": Int64(-qty),
                    "order_claims.order_claimed": Int64(-qty),
                    "order_claims.order_claimable": Int64(qty),
                },
                "$set": {
                    "updated_at": datetime.utcnow(),
                },
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def inc_complete_by_worker(
        self,
        *,
        order_id: str,
        worker_id: str,
        qty: int,
    ) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {
                "order_id": order_id,
                f"worker_claims.{worker_id}": {"$gte": qty},
                "order_status": {
                    "$in": [
                        OrderStatus.CLAIMED,
                        OrderStatus.COMPLETED,
                    ]
                },
            },
            {
                "$inc": {
                    f"worker_claims.{worker_id}": Int64(-qty),
                    "order_claims.order_completed": Int64(qty),
                    "order_claims.order_claimed": Int64(-qty),
                },
                "$set": {
                    "updated_at": datetime.utcnow(),
                },
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def inc_deliver_to_customer(
        self,
        *,
        order_id: str,
        qty: int,
    ) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {
                "order_id": order_id,
                "$expr": {
                    "$gte": [
                        "$order_claims.order_completed",
                        qty,
                    ]
                },
                "order_status": {
                    "$in": [
                        OrderStatus.CLAIMED,
                        OrderStatus.COMPLETED,
                        OrderStatus.DELIVERED,
                    ]
                },
            },
            {
                "$inc": {
                    "order_claims.order_completed": Int64(-qty),
                    "order_claims.order_delivered": Int64(qty),
                },
                "$set": {
                    "updated_at": datetime.utcnow(),
                },
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def unset_worker_claim(
        self,
        order_id: str,
        worker_id: str,
    ) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {
                "order_id": order_id,
                f"worker_claims.{worker_id}": {"$exists": True},
            },
            {
                "$unset": {
                    f"worker_claims.{worker_id}": "",
                },
                "$set": {
                    "updated_at": datetime.utcnow(),
                },
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )