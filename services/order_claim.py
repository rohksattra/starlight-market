"""Service for order claim and unclaim."""
from __future__ import annotations

import logging
from typing import Any

from core.tenant import GameContext
from database.orders import OrderRepo
from models.enums import OrderStatus
from services.tier_limits import TierLimitsService

log = logging.getLogger("services.order_claim")


class OrderClaimService:
    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self.orders = OrderRepo(ctx.db_name)
        self.tier_limits = TierLimitsService(ctx)

    def _validate_qty(self, qty: int, *, action: str) -> None:
        if qty <= 0:
            raise ValueError(f"{action} quantity must be > 0")

    async def _post_unclaim(self, *, order: dict[str, Any], worker_id: str) -> dict[str, Any]:
        if order.get("worker_claims", {}).get(worker_id, 0) <= 0:
            await self.orders.unset_worker_claim(order_id=order["order_id"], worker_id=worker_id)

        if (
            order["order_claims"]["order_claimable"] == order["item_quantity"]
            and order["order_status"] != OrderStatus.NEW
        ):
            await self.orders.update_fields(order["order_id"], {"order_status": OrderStatus.NEW})
            order["order_status"] = OrderStatus.NEW

        return order

    async def _claim_base(self, *, order_id: str, worker_id: str, qty: int, action: str) -> dict[str, Any]:
        self._validate_qty(qty, action=action)
        order = await self.orders.inc_claim(order_id=order_id, worker_id=worker_id, qty=qty)
        if not order:
            raise ValueError("Not enough claimable quantity")
        return order

    async def _unclaim_base(self, *, order_id: str, worker_id: str, qty: int, action: str) -> dict[str, Any]:
        self._validate_qty(qty, action=action)
        order = await self.orders.inc_unclaim(order_id=order_id, worker_id=worker_id, qty=qty)
        if not order:
            raise ValueError("You don't have that many claimed items")
        return await self._post_unclaim(order=order, worker_id=worker_id)

    async def claim(self, *, order_id: str, worker_id: str, qty: int) -> dict[str, Any]:
        await self.tier_limits.validate_worker_claim(
            worker_id=worker_id,
            order_id=order_id,
            quantity=qty,
        )
        return await self._claim_base(order_id=order_id, worker_id=worker_id, qty=qty, action="Claim")

    async def unclaim(self, *, order_id: str, worker_id: str, qty: int) -> dict[str, Any]:
        return await self._unclaim_base(order_id=order_id, worker_id=worker_id, qty=qty, action="Unclaim")

    async def force_claim(self, *, order_id: str, worker_id: str, qty: int) -> dict[str, Any]:
        await self.tier_limits.validate_worker_claim(
            worker_id=worker_id,
            order_id=order_id,
            quantity=qty,
        )
        return await self._claim_base(order_id=order_id, worker_id=worker_id, qty=qty, action="Force claim")

    async def force_unclaim(self, *, order_id: str, worker_id: str, qty: int) -> dict[str, Any]:
        return await self._unclaim_base(
            order_id=order_id,
            worker_id=worker_id,
            qty=qty,
            action="Force unclaim",
        )
