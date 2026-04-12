# app/services/claimable_service.py
from __future__ import annotations

from typing import List, Dict, Any
from app.repositories.claimable_repo import ClaimableRepository


class ClaimableService:
    def __init__(self) -> None:
        self.repo = ClaimableRepository()

    async def list_claimable(self) -> List[Dict[str, Any]]:
        orders = await self.repo.get_claimable_orders()
        orders.sort(key=lambda o: o.get("order_number", 0))

        return [
            {
                "order_number": o.get("order_number", 0),
                "item_name": o.get("item_name", "Unknown"),
                "item_emoji": o.get("item_emoji", "🌟"),
                "value": o["order_claims"]["order_claimable"],
                "channel_id": o.get("channel_id"),
            }
            for o in orders
        ]