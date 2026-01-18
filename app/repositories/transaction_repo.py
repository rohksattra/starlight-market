# app/repositories/transaction_repo.py
from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime
from bson.int64 import Int64

from db.mongo import get_db


TransactionData = Dict[str, Any]


class TransactionRepository:
    def __init__(self) -> None:
        self.transactions = get_db().transactions

    async def create_transaction(self, transaction: TransactionData) -> bool:
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
        )
        return result.matched_count == 0

    async def get_by_id(self, transaction_id: str) -> Optional[TransactionData]:
        return await self.transactions.find_one(
            {"transaction_id": transaction_id},
            {"_id": 0},
        )
