"""Mongo queries for the items collection."""
from __future__ import annotations

from typing import Any

from bson.int64 import Int64
from pymongo import ReturnDocument

from core.time import utc_now
from database.connection import get_db
from models.item import Item

Session = Any


class ItemRepo:
    def __init__(self, db_name: str) -> None:
        self.items = get_db(db_name).items

    def _session_kw(self, session: Session | None) -> dict:
        return {} if session is None else {"session": session}

    async def get_categories(self) -> list[str]:
        return await self.items.distinct("item_category")

    async def get_by_category(self, category: str) -> list[Item]:
        return await self.items.find({"item_category": category}, {"_id": 0}).to_list(None)

    async def get_by_id(self, item_id: str) -> Item | None:
        return await self.items.find_one({"item_id": item_id}, {"_id": 0})

    async def get_all(self, *, limit: int = 5000) -> list[Item]:
        return await self.items.find({}, {"_id": 0}).limit(limit).to_list(length=limit)

    async def update_item_price(self, *, item_id: str, new_price: int) -> Item | None:
        return await self.items.find_one_and_update(
            {"item_id": item_id},
            {
                "$set": {
                    "item_price": Int64(new_price),
                    "updated_at": utc_now(),
                }
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def rename_item(self, *, item_id: str, new_name: str) -> Item | None:
        return await self.items.find_one_and_update(
            {"item_id": item_id},
            {
                "$set": {
                    "item_name": new_name,
                    "updated_at": utc_now(),
                }
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def rename_category(self, *, old_name: str, new_name: str) -> int:
        res = await self.items.update_many(
            {"item_category": old_name},
            {"$set": {"item_category": new_name, "updated_at": utc_now()}},
        )
        return res.modified_count

    async def inc_item_sold(
        self,
        *,
        item_id: str,
        qty: int,
        session: Session | None = None,
    ) -> None:
        await self.items.update_one(
            {"item_id": item_id, "item_sold": None},
            {"$set": {"item_sold": Int64(0)}},
            **self._session_kw(session),
        )
        await self.items.update_one(
            {"item_id": item_id},
            {
                "$inc": {"item_sold": Int64(qty)},
                "$set": {"updated_at": utc_now()},
            },
            upsert=True,
            **self._session_kw(session),
        )

    async def sum_item_sold(self) -> int:
        docs = await self.items.aggregate(
            [{"$group": {"_id": None, "total": {"$sum": "$item_sold"}}}]
        ).to_list(length=1)
        if not docs:
            return 0
        return int(docs[0].get("total") or 0)
