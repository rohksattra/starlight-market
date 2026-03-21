#app/services/claimable_service.py
from __future__ import annotations

from typing import List, Dict, Any
from app.repositories.claimable_repo import ClaimableRepository


class ClaimableService:
    def __init__(self) -> None:
        self.repo = ClaimableRepository()

    async def list_claimable(self) -> List[Dict[str, Any]]:
        orders = await self.repo.get_claimable_orders()

        return [
            {
                "name": f"Order #{o['order_number']} • {o.get('item_name', 'Unknown')}",
                "value": o["order_claims"]["order_claimable"],
                "channel_id": o.get("channel_id"),
            }
            for o in orders
        ]