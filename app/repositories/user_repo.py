from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from bson.int64 import Int64

from db.mongo import get_db
from app.domains.user_domain import User


UserData = User


class UserRepository:
    def __init__(self) -> None:
        self.users = get_db().users

    async def get_user(self, user_id: str) -> Optional[UserData]:
        return await self.users.find_one({"user_id": user_id}, {"_id": 0})

    async def ensure_user(self, user_id: str) -> None:
        now = datetime.utcnow()
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "donation_given": Int64(0),
                    "total_customer_order": Int64(0),
                    "total_customer_spent": Int64(0),
                    "total_worker_finished_item": Int64(0),
                    "total_worker_income": Int64(0),
                    "count_worker_rating": Int64(0),
                    "total_worker_star": Int64(0),
                    "counting_score": Int64(0),
                },
                "$set": {"updated_at": now},
            },
            upsert=True,
        )

    async def inc_customer_order(self, *, user_id: str, qty: int = 1) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"total_customer_order": Int64(qty)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def inc_customer_spent(self, *, user_id: str, amount: int) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"total_customer_spent": Int64(amount)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def inc_donation_given(self, *, user_id: str, amount: int) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"donation_given": Int64(amount)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def inc_worker_income(self, *, user_id: str, finished_item_inc: int = 0, income_inc: int = 0) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {
                    "total_worker_finished_item": Int64(finished_item_inc),
                    "total_worker_income": Int64(income_inc),
                },
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def inc_worker_rating(self, *, user_id: str, rating: int) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {
                    "count_worker_rating": Int64(1),
                    "total_worker_star": Int64(rating),
                },
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def inc_counting_score(self, *, user_id: str, points: int) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"counting_score": Int64(points)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def get_rank_customer(self, user_id: str) -> int | None:
        doc = await self.users.find_one(
            {"user_id": user_id},
            {"total_customer_spent": 1},
        )
        if not doc:
            return None
        spent = int(doc.get("total_customer_spent", 0))
        higher = await self.users.count_documents(
            {"total_customer_spent": {"$gt": spent}}
        )
        return higher + 1

    async def get_rank_worker(self, user_id: str) -> int | None:
        doc = await self.users.find_one(
            {"user_id": user_id},
            {"total_worker_income": 1},
        )
        if not doc:
            return None
        income = int(doc.get("total_worker_income", 0))
        higher = await self.users.count_documents(
            {"total_worker_income": {"$gt": income}}
        )
        return higher + 1

    async def get_rank_donor(self, user_id: str) -> int | None:
        doc = await self.users.find_one(
            {"user_id": user_id},
            {"donation_given": 1},
        )
        if not doc:
            return None
        given = int(doc.get("donation_given", 0))
        if given <= 0:
            return None
        higher = await self.users.count_documents({"donation_given": {"$gt": given}})
        return higher + 1

    async def find_users_by_ids(self, user_ids: list[str]) -> dict[str, UserData]:
        if not user_ids:
            return {}
        out: dict[str, UserData] = {}
        cursor = self.users.find({"user_id": {"$in": user_ids}}, {"_id": 0})
        async for doc in cursor:
            uid = doc.get("user_id")
            if uid is not None:
                out[str(uid)] = doc
        return out
