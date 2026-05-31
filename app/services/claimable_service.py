from __future__ import annotations

from typing import Any, Dict, List

from app.repositories.claimable_repo import ClaimableRepository
from app.repositories.item_repo import ItemRepository


class ClaimableService:
    def __init__(self) -> None:
        self.repo = ClaimableRepository()
        self.items = ItemRepository()

    async def _inject_item_emoji(
        self,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not rows:
            return rows

        item_ids = {
            r["item_id"]
            for r in rows
            if r.get("item_id")
        }

        db_items = await self.items.get_all()

        emoji_map = {
            i["item_id"]: i.get("item_emoji") or "🌟"
            for i in db_items
            if i["item_id"] in item_ids
        }

        for r in rows:
            r["item_emoji"] = emoji_map.get(r.get("item_id")) or "🌟"

        return rows

    async def list_claimable(self) -> List[Dict[str, Any]]:
        orders = await self.repo.get_claimable_orders()
        orders.sort(key=lambda o: o.get("order_number", 0))

        rows = [
            {
                "order_number": o.get("order_number", 0),
                "item_id": o.get("item_id"),
                "item_name": o.get("item_name", "Unknown"),
                "value": o["order_claims"]["order_claimable"],
                "channel_id": o.get("channel_id"),
            }
            for o in orders
        ]

        return await self._inject_item_emoji(rows)