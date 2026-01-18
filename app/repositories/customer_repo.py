# app/repositories/customer_repo.py
from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime

from db.mongo import get_db


CustomerData = Dict[str, Any]


class CustomerRepository:
    def __init__(self) -> None:
        self.customers = get_db().customers

    async def get_customer(self, customer_id: str) -> Optional[CustomerData]:
        return await self.customers.find_one({"customer_id": customer_id}, {"_id": 0})

    async def ensure_customer(self, customer_id: str) -> None:
        await self.customers.update_one(
            {"customer_id": customer_id},
            {
                "$setOnInsert": {
                    "customer_id": customer_id,
                    "total_customer_order": 0,
                    "total_customer_spent": 0,
                },
                 "$set": {
                     "updated_at": datetime.utcnow()
                     },
            },
            upsert=True,
        )

    async def inc_customer_order(self, *, customer_id: str, qty: int = 1) -> None:
        await self.customers.update_one(
            {"customer_id": customer_id},
            {
                "$inc": {"total_customer_order": qty},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def inc_customer_spent(self, *, customer_id: str, amount: int) -> None:
        await self.customers.update_one(
            {"customer_id": customer_id},
            {
                "$inc": {"total_customer_spent": amount},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def get_rank_customer(self, customer_id: str) -> int | None:
        doc = await self.customers.find_one(
            {"customer_id": customer_id},
            {"total_customer_spent": 1},
        )
        if not doc:
            return None
        spent = int(doc.get("total_customer_spent", 0))
        higher = await self.customers.count_documents(
            {"total_customer_spent": {"$gt": spent}}
        )
        return higher + 1
