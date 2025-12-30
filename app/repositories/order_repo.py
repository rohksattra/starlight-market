# app/repositories/order_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from pymongo import ReturnDocument

from db.mongo import get_db
from app.domains.enums.order_status_enum import OrderStatus


OrderData = Dict[str, Any]


class OrderRepository:
    def __init__(self) -> None:
        self.orders = get_db().orders

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

    async def get_last_order_number(self) -> int:
        doc = await self.orders.find_one(
            {},
            sort=[("order_number", -1)],
            projection={"order_number": 1},
        )
        return int(doc["order_number"]) if doc else 0

    async def count_active_by_worker(self, worker_id: str) -> int:
        return await self.orders.count_documents(
            {f"worker_claims.{worker_id}": {"$gt": 0}}
        )

    async def count_active_by_customer(self, customer_id: str) -> int:
        return await self.orders.count_documents(
            {
                "customer_id": customer_id,
                "order_status": {
                    "$in": [
                        OrderStatus.NEW,
                        OrderStatus.CLAIMED,
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

    async def create_order(self, order: OrderData) -> None:
        now = datetime.utcnow()
        await self.orders.update_one(
            {"order_id": order["order_id"]},
            {
                "$setOnInsert": {
                    **order,
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

    async def update_fields(self, order_id: str, fields: Dict[str, Any]) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {"order_id": order_id},
            {"$set": {**fields, "updated_at": datetime.utcnow()}},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def set_channel(self, order_id: str, channel_id: str) -> None:
        await self.orders.update_one(
            {"order_id": order_id},
            {"$set": {"channel_id": channel_id, "updated_at": datetime.utcnow()}},
        )

    async def set_embed_message(self, order_id: str, message_id: str) -> None:
        await self.orders.update_one(
            {"order_id": order_id},
            {"$set": {"embed_message_id": message_id, "updated_at": datetime.utcnow()}},
        )

    async def get_active_by_worker(self, worker_id: str) -> List[OrderData]:
        cursor = self.orders.find(
            {f"worker_claims.{worker_id}": {"$gt": 0}},
            {"_id": 0},
        )
        return [doc async for doc in cursor]

    async def get_active_by_customer(self, customer_id: str) -> List[OrderData]:
        cursor = self.orders.find(
            {
                "customer_id": customer_id,
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

    async def inc_claim(self, *, order_id: str, worker_id: str, qty: int) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {
                "order_id": order_id,
                "order_status": {"$in": [OrderStatus.NEW, OrderStatus.CLAIMED]},
                "order_claims.order_claimable": {"$gte": qty},
            },
            {
                "$inc": {
                    f"worker_claims.{worker_id}": qty,
                    "order_claims.order_claimed": qty,
                    "order_claims.order_claimable": -qty,
                },
                "$set": {
                    "order_status": OrderStatus.CLAIMED,
                    "updated_at": datetime.utcnow(),
                },
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def inc_unclaim(self, *, order_id: str, worker_id: str, qty: int) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {
                "order_id": order_id,
                f"worker_claims.{worker_id}": {"$gte": qty},
                "order_status": {"$in": [OrderStatus.NEW, OrderStatus.CLAIMED]},
            },
            {
                "$inc": {
                    f"worker_claims.{worker_id}": -qty,
                    "order_claims.order_claimed": -qty,
                    "order_claims.order_claimable": qty,
                },
                "$set": {"updated_at": datetime.utcnow()},
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def inc_complete_by_worker(self, *, order_id: str, worker_id: str, qty: int) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {
                "order_id": order_id,
                f"worker_claims.{worker_id}": {"$gte": qty},
                "order_status": {"$in": [OrderStatus.CLAIMED, OrderStatus.COMPLETED]},
            },
            {
                "$inc": {
                    f"worker_claims.{worker_id}": -qty,
                    "order_claims.order_completed": qty,
                    "order_claims.order_claimed": -qty,
                },
                "$set": {"updated_at": datetime.utcnow()},
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def inc_deliver_to_customer(self, *, order_id: str, qty: int) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {
                "order_id": order_id,
                "$expr": {
                    "$gte": [
                        "$order_claims.order_completed",
                        qty,
                    ]
                },
                "order_status": {"$in": [OrderStatus.CLAIMED, OrderStatus.COMPLETED, OrderStatus.DELIVERED]},
            },
            {
                "$inc": {
                    "order_claims.order_completed": -qty,
                    "order_claims.order_delivered": qty,
                },
                "$set": {"updated_at": datetime.utcnow()},
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def unset_worker_claim(self, order_id: str, worker_id: str) -> Optional[OrderData]:
        return await self.orders.find_one_and_update(
            {
                "order_id": order_id,
                f"worker_claims.{worker_id}": {"$exists": True},
            },
            {
                "$unset": {f"worker_claims.{worker_id}": ""},
                "$set": {"updated_at": datetime.utcnow()},
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
