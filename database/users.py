"""Mongo queries for the users collection."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from bson.int64 import Int64

from database.connection import get_db
from database.user_defaults import new_user_fields
from models.user import User
from services.tiers import current_coupon_month_key

Session = Any


class UserRepo:
    def __init__(self, db_name: str) -> None:
        self.users = get_db(db_name).users

    def _session_kw(self, session: Session | None) -> dict:
        return {} if session is None else {"session": session}

    async def get_user(self, user_id: str) -> User | None:
        return await self.users.find_one({"user_id": user_id}, {"_id": 0})

    async def ensure_user(self, user_id: str, *, session: Session | None = None) -> None:
        now = datetime.utcnow()
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$setOnInsert": new_user_fields(user_id=user_id),
                "$set": {"updated_at": now},
            },
            upsert=True,
            **self._session_kw(session),
        )

    async def inc_customer_order(
        self,
        *,
        user_id: str,
        qty: int = 1,
        session: Session | None = None,
    ) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"total_customer_order": Int64(qty)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
            **self._session_kw(session),
        )

    async def dec_customer_order(
        self,
        *,
        user_id: str,
        qty: int = 1,
        session: Session | None = None,
    ) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"total_customer_order": Int64(-qty)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            **self._session_kw(session),
        )

    async def transfer_customer_order_count(
        self,
        *,
        from_user_id: str,
        to_user_id: str,
        session: Session | None = None,
    ) -> None:
        await self.dec_customer_order(user_id=from_user_id, session=session)
        await self.ensure_user(to_user_id, session=session)
        await self.inc_customer_order(user_id=to_user_id, session=session)

    async def get_coupons_used(self, user_id: str) -> int:
        doc = await self.get_user(user_id)
        if not doc:
            return 0
        month_key = current_coupon_month_key()
        stored_month = int(doc.get("coupons_used_month", 0) or 0)
        if stored_month != month_key:
            return 0
        return int(doc.get("coupons_used_count", 0) or 0)

    async def try_consume_coupon(
        self,
        *,
        user_id: str,
        max_coupons: int,
        session: Session | None = None,
    ) -> bool:
        if max_coupons <= 0:
            return False

        month_key = current_coupon_month_key()
        doc = await self.users.find_one(
            {"user_id": user_id},
            {"coupons_used_month": 1, "coupons_used_count": 1},
            **self._session_kw(session),
        )
        used = 0
        if doc and int(doc.get("coupons_used_month", 0) or 0) == month_key:
            used = int(doc.get("coupons_used_count", 0) or 0)
        if used >= max_coupons:
            return False

        await self.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "coupons_used_month": Int64(month_key),
                    "coupons_used_count": Int64(used + 1),
                    "updated_at": datetime.utcnow(),
                }
            },
            upsert=True,
            **self._session_kw(session),
        )
        return True

    async def refund_coupon(self, *, user_id: str, session: Session | None = None) -> None:
        month_key = current_coupon_month_key()
        doc = await self.users.find_one(
            {"user_id": user_id},
            {"coupons_used_month": 1, "coupons_used_count": 1},
            **self._session_kw(session),
        )
        if not doc:
            return
        if int(doc.get("coupons_used_month", 0) or 0) != month_key:
            return
        used = int(doc.get("coupons_used_count", 0) or 0)
        if used <= 0:
            return

        await self.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "coupons_used_count": Int64(used - 1),
                    "updated_at": datetime.utcnow(),
                }
            },
            **self._session_kw(session),
        )

    async def inc_worker_income(
        self,
        *,
        user_id: str,
        finished_item_inc: int = 0,
        income_inc: int = 0,
        session: Session | None = None,
    ) -> None:
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
            **self._session_kw(session),
        )

    async def inc_customer_spent(
        self,
        *,
        user_id: str,
        amount: int,
        session: Session | None = None,
    ) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"total_customer_spent": Int64(amount)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
            **self._session_kw(session),
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

    async def get_rank_customer(self, user_id: str) -> int | None:
        doc = await self.users.find_one({"user_id": user_id}, {"total_customer_spent": 1})
        if not doc:
            return None
        spent = int(doc.get("total_customer_spent", 0))
        higher = await self.users.count_documents({"total_customer_spent": {"$gt": spent}})
        return higher + 1

    async def get_rank_worker(self, user_id: str) -> int | None:
        doc = await self.users.find_one({"user_id": user_id}, {"total_worker_income": 1})
        if not doc:
            return None
        income = int(doc.get("total_worker_income", 0))
        higher = await self.users.count_documents({"total_worker_income": {"$gt": income}})
        return higher + 1

    async def get_rank_donor(self, user_id: str) -> int | None:
        doc = await self.users.find_one({"user_id": user_id}, {"donation_given": 1})
        if not doc:
            return None
        given = int(doc.get("donation_given", 0))
        if given <= 0:
            return None
        higher = await self.users.count_documents({"donation_given": {"$gt": given}})
        return higher + 1

    async def search_user_ids(self, query: str, *, limit: int = 25) -> list[str]:
        import re

        safe = re.escape(query.strip())
        if not safe:
            return []
        cursor = self.users.find(
            {"user_id": {"$regex": safe}},
            {"user_id": 1, "_id": 0},
        ).limit(limit)
        return [str(doc["user_id"]) async for doc in cursor]

    async def inc_game_score(
        self,
        *,
        user_id: str,
        game_type: str,
        score_points: int,
        market_points: int,
    ) -> None:
        from models.games import GAME_SCORE_FIELDS

        if game_type not in GAME_SCORE_FIELDS or game_type == "global":
            raise ValueError("Invalid game type")

        field = GAME_SCORE_FIELDS[game_type]  # type: ignore[index]
        await self.ensure_user(user_id)
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {
                    field: Int64(score_points),
                    "market_points": Int64(market_points),
                },
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
