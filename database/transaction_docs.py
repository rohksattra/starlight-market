"""Mongo queries for the transactions collection (market payments)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from bson.int64 import Int64

from database.connection import get_db
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
                    "created_at": transaction.get("created_at") or datetime.utcnow(),
                }
            },
            upsert=True,
            **self._session_kw(session),
        )
        return result.matched_count == 0
