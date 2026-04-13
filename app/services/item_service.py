# app/services/item_service.py
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.repositories.item_repo import ItemRepository


log = logging.getLogger("services.item_service")


class ItemService:
    def __init__(self) -> None:
        self.items = ItemRepository()

    def _validate_non_empty(self, *values: str) -> None:
        if any(not v.strip() for v in values):
            raise ValueError("Value cannot be empty")

    def _validate_price(self, price: int) -> None:
        if price <= 0:
            raise ValueError("Price must be > 0")

    async def list_categories(self) -> List[str]:
        categories = await self.items.get_categories()
        log.debug("List categories | count=%s", len(categories))
        return categories

    async def list_items(self) -> List[Dict[str, Any]]:
        items = await self.items.get_all()
        log.debug("List items | count=%s", len(items))
        return items

    async def list_items_by_category(self, category: str) -> List[Dict[str, Any]]:
        if not category.strip():
            log.warning("List items failed | empty category")
            return []
        items = await self.items.get_by_category(category)
        log.info("List items | category=%s count=%s", category, len(items))
        return items

    async def list_item_price_by_category(self, category: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        if not category.strip():
            log.warning("List item price failed | empty category")
            return []

        items = await self.items.get_by_category(category)
        items.sort(key=lambda x: x["item_name"].lower())

        if limit > 0:
            items = items[:limit]

        log.debug("List item price | category=%s count=%s limit=%s", category, len(items), limit)
        return items

    async def get_item_emoji(self, item_id: str) -> str:
        item = await self.items.get_by_id(item_id)
        if not item:
            log.warning("Get item emoji failed | item not found | item_id=%s", item_id)
            return "❓"
        return item.get("item_emoji", "❓")

    async def update_category_name(self, *, old_name: str, new_name: str) -> None:
        self._validate_non_empty(old_name, new_name)

        updated = await self.items.rename_category(old_name=old_name, new_name=new_name)
        if updated == 0:
            raise ValueError("Category not found")

        log.info("Category renamed | from=%s to=%s count=%s", old_name, new_name, updated)

    async def update_item_name(self, *, item_id: str, new_name: str) -> None:
        self._validate_non_empty(new_name)

        if not await self.items.rename_item(item_id=item_id, new_name=new_name):
            raise ValueError("Item not found")

        log.info("Item renamed | item_id=%s new_name=%s", item_id, new_name)

    async def update_price(self, item_id: str, new_price: int) -> None:
        self._validate_price(new_price)

        if not await self.items.update_item_price(item_id=item_id, new_price=new_price):
            raise ValueError("Item not found")

        log.info("Item price updated | item_id=%s new_price=%s", item_id, new_price)