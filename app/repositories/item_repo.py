# app/repositories/item_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime
from bson.int64 import Int64

from pymongo import ReturnDocument

from db.mongo import get_db


ItemData = Dict[str, Any]


class ItemRepository:
    def __init__(self) -> None:
        self.items = get_db().items

    async def get_categories(self) -> List[str]:
        return await self.items.distinct("item_category")

    async def get_all(self) -> List[ItemData]:
        return await self.items.find({}, {"_id": 0}).to_list(None)

    async def get_by_category(self, category: str) -> List[ItemData]:
        return await self.items.find(
            {"item_category": category},
            {"_id": 0},
        ).to_list(None)

    async def get_by_id(self, item_id: str) -> Optional[ItemData]:
        return await self.items.find_one(
            {"item_id": item_id},
            {"_id": 0},
        )

    async def get_by_name(self, *, category: str, name: str) -> Optional[ItemData]:
        return await self.items.find_one(
            {"item_category": category, "item_name": name},
            {"_id": 0},
        )

    async def count_by_category(self, category: str) -> int:
        return await self.items.count_documents({"item_category": category})

    async def update_item_price(self, *, item_id: str, new_price: int) -> Optional[ItemData]:
        return await self.items.find_one_and_update(
            {"item_id": item_id},
            {
                "$set": {
                    "item_price": Int64(new_price),
                    "updated_at": datetime.utcnow(),
                }
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def rename_item(self, *, item_id: str, new_name: str) -> Optional[ItemData]:
        return await self.items.find_one_and_update(
            {"item_id": item_id},
            {
                "$set": {
                    "item_name": new_name,
                    "updated_at": datetime.utcnow(),
                }
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def rename_category(self, *, old_name: str, new_name: str) -> int:
        res = await self.items.update_many(
            {"item_category": old_name},
            {"$set": {"item_category": new_name, "updated_at": datetime.utcnow()}},
        )
        return res.modified_count

    async def delete_item(self, *, item_id: str) -> bool:
        res = await self.items.delete_one({"item_id": item_id})
        return res.deleted_count == 1

    async def delete_item_by_category(self, *, category: str) -> int:
        res = await self.items.delete_many({"item_category": category})
        return res.deleted_count

    async def inc_item_sold(self, *, item_id: str, qty: int) -> None:
        await self.items.update_one(
            {"item_id": item_id, "item_sold": None},
            {"$set": {"item_sold": Int64(0)}},
        )
        await self.items.update_one(
            {"item_id": item_id},
            {
                "$inc": {"item_sold": Int64(qty)},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
        )
