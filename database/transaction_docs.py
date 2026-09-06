"""Mongo queries for the transactions collection (market payments)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from bson.int64 import Int64

from core.time import utc_now
from database.connection import get_db
from models.enums import ServerRole
from models.transaction import Transaction

Session = Any


class TransactionRepo:
    def __init__(self, db_name: str) -> None:
        self.transactions = get_db(db_name).transactions

    def _session_kw(self, session: Session | None) -> dict:
        return {} if session is None else {"session": session}

    async def create_transaction(
        self,
        transaction: Transaction,
        *,
        session: Session | None = None,
    ) -> bool:
        result = await self.transactions.update_one(
            {"transaction_id": transaction["transaction_id"]},
            {
                "$setOnInsert": {
                    **transaction,
                    "item_quantity": Int64(transaction["item_quantity"]),
                    "total_price": Int64(transaction["total_price"]),
                    "created_at": transaction.get("created_at") or utc_now(),
                }
            },
            upsert=True,
            **self._session_kw(session),
        )
        return result.matched_count == 0

    def _match(self, *, role: ServerRole | None, since: datetime | None) -> dict[str, Any]:
        match: dict[str, Any] = {}
        if role is not None:
            match["user_role"] = role
        if since is not None:
            match["created_at"] = {"$gte": since}
        return match

    async def _sum_field(
        self,
        *,
        field: str,
        role: ServerRole,
        since: datetime | None,
    ) -> int:
        pipeline = [
            {"$match": self._match(role=role, since=since)},
            {"$group": {"_id": None, "total": {"$sum": f"${field}"}}},
        ]
        docs = await self.transactions.aggregate(pipeline).to_list(length=1)
        if not docs:
            return 0
        return int(docs[0].get("total") or 0)

    async def sum_total_price(self, *, role: ServerRole, since: datetime | None) -> int:
        return await self._sum_field(field="total_price", role=role, since=since)

    async def sum_item_quantity(self, *, role: ServerRole, since: datetime | None) -> int:
        return await self._sum_field(field="item_quantity", role=role, since=since)

    async def top_users(
        self,
        *,
        role: ServerRole,
        since: datetime | None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        pipeline = [
            {"$match": self._match(role=role, since=since)},
            {"$group": {"_id": "$user_id", "value": {"$sum": "$total_price"}}},
            {"$match": {"value": {"$gt": 0}}},
            {"$sort": {"value": -1}},
            {"$limit": limit},
        ]
        return [
            {"id": d["_id"], "value": int(d["value"])}
            async for d in self.transactions.aggregate(pipeline)
        ]

    async def top_items(self, *, since: datetime | None, limit: int = 100) -> list[dict[str, Any]]:
        match = self._match(role=ServerRole.CUSTOMER, since=since)
        match["item_id"] = {"$nin": ["", None]}
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$item_id", "value": {"$sum": "$item_quantity"}}},
            {"$match": {"value": {"$gt": 0}}},
            {"$sort": {"value": -1}},
            {"$limit": limit},
        ]
        return [
            {"item_id": d["_id"], "value": int(d["value"])}
            async for d in self.transactions.aggregate(pipeline)
        ]

    async def delete_created_before(self, cutoff: datetime) -> int:
        result = await self.transactions.delete_many({"created_at": {"$lt": cutoff}})
        return int(result.deleted_count)
