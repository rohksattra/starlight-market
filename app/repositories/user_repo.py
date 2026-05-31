from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from bson.int64 import Int64
from db.mongo import get_db
from db.user_defaults import new_user_fields
from app.domains.user_domain import User


UserData = User
Session = Any


class UserRepository:
    def __init__(self) -> None:
        self.users = get_db().users

    def _session_kw(self, session: Session | None) -> dict:
        return {} if session is None else {"session": session}

    async def get_user(self, user_id: str) -> Optional[UserData]:
        return await self.users.find_one({"user_id": user_id}, {"_id": 0})

    async def search_user_ids(self, query: str, *, limit: int = 25) -> list[str]:
        safe = re.escape(query.strip())
        if not safe:
            return []
        cursor = self.users.find(
            {"user_id": {"$regex": safe}},
            {"user_id": 1, "_id": 0},
        ).limit(limit)
        return [str(doc["user_id"]) async for doc in cursor]

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

    async def inc_customer_order(self, *, user_id: str, qty: int = 1, session: Session | None = None) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"total_customer_order": Int64(qty)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
            **self._session_kw(session),
        )

    async def dec_customer_order(self, *, user_id: str, qty: int = 1, session: Session | None = None) -> None:
        doc = await self.users.find_one(
            {"user_id": user_id},
            {"total_customer_order": 1},
            **self._session_kw(session),
        )
        if not doc:
            return
        new_val = max(0, int(doc.get("total_customer_order", 0)) - qty)
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "total_customer_order": Int64(new_val),
                    "updated_at": datetime.utcnow(),
                }
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

    async def inc_customer_spent(self, *, user_id: str, amount: int, session: Session | None = None) -> None:
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

    async def _inc_with_defaults(
        self,
        *,
        user_id: str,
        inc_fields: dict[str, int],
        session: Session | None = None,
    ) -> None:
        await self.users.update_one(
            {"user_id": user_id},
            {
                "$setOnInsert": new_user_fields(user_id=user_id),
                "$inc": {k: Int64(v) for k, v in inc_fields.items()},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
            **self._session_kw(session),
        )

    async def inc_starlight_points(self, *, user_id: str, points: int) -> None:
        await self._inc_with_defaults(
            user_id=user_id,
            inc_fields={"starlight_points": points},
        )

    async def inc_game_score(
        self,
        *,
        user_id: str,
        game_type: str,
        score_points: int,
        starlight_points: int,
    ) -> None:
        from app.domains.game_domain import GAME_SCORE_FIELDS

        if game_type not in GAME_SCORE_FIELDS or game_type == "global":
            raise ValueError("Invalid game type")

        field = GAME_SCORE_FIELDS[game_type]
        await self._inc_with_defaults(
            user_id=user_id,
            inc_fields={field: score_points, "starlight_points": starlight_points},
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
