"""Service for items: list categories, items, update price/name."""
from __future__ import annotations

import logging
from typing import Any

from core.tenant import GameContext
from database.items import ItemRepo
from services.catalog_cache import filter_items, invalidate_items, item_map, items as cached_items

log = logging.getLogger("services.items")


class ItemService:
    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self.items = ItemRepo(ctx.db_name)

    async def list_categories(self) -> list[str]:
        names = {str(item.get("item_category") or "") for item in await cached_items(self.ctx.db_name)}
        return sorted(name for name in names if name)

    async def list_items(self) -> list[dict[str, Any]]:
        return list(await cached_items(self.ctx.db_name))

    async def list_items_by_category(self, category: str) -> list[dict[str, Any]]:
        if not category.strip():
            return []
        return [
            item
            for item in await cached_items(self.ctx.db_name)
            if str(item.get("item_category") or "") == category
        ]

    async def list_item_price_by_category(
        self,
        category: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if not category.strip():
            log.warning("List item price failed | empty category")
            return []

        result = [
            {
                "item_id": item.get("item_id"),
                "item_name": item.get("item_name", "Unknown Item"),
                "item_price": int(item.get("item_price", 0)),
                "item_emoji": item.get("item_emoji") or "🌟",
            }
            for item in await self.list_items_by_category(category)
        ]
        result.sort(key=lambda x: str(x["item_name"]).lower())
        if limit > 0:
            result = result[:limit]
        return result

    async def get_by_id(self, item_id: str) -> dict[str, Any] | None:
        return await self.items.get_by_id(item_id)

    async def get_item_emoji(self, item_id: str) -> str:
        item = (await item_map(self.ctx.db_name)).get(str(item_id))
        return (item.get("item_emoji") if item else None) or "🌟"

    async def search_items(
        self,
        query: str,
        *,
        limit: int = 25,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        return filter_items(
            await cached_items(self.ctx.db_name),
            query,
            limit=limit,
            category=category,
        )

    @staticmethod
    def _validate_non_empty(*values: str) -> None:
        if any(not v.strip() for v in values):
            raise ValueError("Value cannot be empty")

    @staticmethod
    def _validate_price(price: int) -> None:
        if price < 0:
            raise ValueError("Price cannot be negative")

    async def update_category_name(self, *, old_name: str, new_name: str) -> None:
        self._validate_non_empty(old_name, new_name)
        updated = await self.items.rename_category(
            old_name=old_name,
            new_name=new_name.strip(),
        )
        if updated == 0:
            raise ValueError("Category not found")
        invalidate_items(self.ctx.db_name)
        log.info(
            "Category renamed | game=%s from=%s to=%s count=%s",
            self.ctx.game,
            old_name,
            new_name.strip(),
            updated,
        )

    async def update_item_name(self, *, item_id: str, new_name: str) -> None:
        self._validate_non_empty(new_name)
        if not await self.items.rename_item(item_id=item_id, new_name=new_name.strip()):
            raise ValueError("Item not found")
        invalidate_items(self.ctx.db_name)
        log.info(
            "Item renamed | game=%s item_id=%s new_name=%s",
            self.ctx.game,
            item_id,
            new_name.strip(),
        )

    async def update_item_price(self, *, item_id: str, new_price: int) -> None:
        self._validate_price(new_price)
        if not await self.items.update_item_price(item_id=item_id, new_price=new_price):
            raise ValueError("Item not found")
        invalidate_items(self.ctx.db_name)
        log.info(
            "Item price updated | game=%s item_id=%s new_price=%s",
            self.ctx.game,
            item_id,
            new_price,
        )

