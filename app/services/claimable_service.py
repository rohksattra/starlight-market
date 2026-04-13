# app/services/claimable_service.py
from __future__ import annotations

from typing import List, Dict, Any

from app.repositories.claimable_repo import ClaimableRepository
from app.repositories.item_repo import ItemRepository


class ClaimableService:
    def __init__(self) -> None:
        self.repo = ClaimableRepository()
        self.items = ItemRepository()

    async def _inject_item_emoji(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not rows:
            return rows

        item_names = {r["item_name"] for r in rows}

        db_items = await self.items.get_all()
        emoji_map = {
            i["item_name"]: i.get("item_emoji", "🌟")
            for i in db_items
            if i["item_name"] in item_names
        }

        for r in rows:
            r["item_emoji"] = emoji_map.get(r["item_name"], "🌟")

        return rows

    async def list_claimable(self) -> List[Dict[str, Any]]:
        orders = await self.repo.get_claimable_orders()
        orders.sort(key=lambda o: o.get("order_number", 0))

        rows = [
            {
                "order_number": o.get("order_number", 0),
                "item_name": o.get("item_name", "Unknown"),
                "value": o["order_claims"]["order_claimable"],
                "channel_id": o.get("channel_id"),
            }
            for o in orders
        ]

        return await self._inject_item_emoji(rows)