# app/services/order_claim_service.py
from __future__ import annotations

import logging
from typing import Any, Dict

from app.domains.enums.order_status_enum import OrderStatus
from app.repositories.order_repo import OrderRepository


log = logging.getLogger("services.order_claim_service")


class OrderClaimService:
    def __init__(self) -> None:
        self.orders = OrderRepository()

    def _validate_qty(self, qty: int, *, action: str) -> None:
        if qty <= 0:
            raise ValueError(f"{action} quantity must be > 0")

    async def _post_unclaim(self, *, order: Dict[str, Any], worker_id: str) -> Dict[str, Any]:
        if order.get("worker_claims", {}).get(worker_id, 0) <= 0:
            await self.orders.unset_worker_claim(order_id=order["order_id"], worker_id=worker_id)
            log.info("Worker claim unset | order_id=%s worker=%s", order["order_id"], worker_id)
        if (order["order_claims"]["order_claimable"] == order["item_quantity"] and order["order_status"] != OrderStatus.NEW):
            await self.orders.update_fields(order["order_id"], {"order_status": OrderStatus.NEW})
            order["order_status"] = OrderStatus.NEW
            log.info("Order status reverted | order_id=%s status=%s", order["order_id"], OrderStatus.NEW)
        return order

    async def claim(self, *, order_id: str, worker_id: str, qty: int) -> Dict[str, Any]:
        self._validate_qty(qty, action="Claim")
        order = await self.orders.inc_claim(order_id=order_id, worker_id=worker_id, qty=qty)
        if not order:
            log.warning("Claim failed | insufficient qty or invalid state | order_id=%s worker=%s qty=%s", order_id, worker_id, qty)
            raise ValueError("Not enough claimable quantity")
        log.info("Claim success | order_id=%s worker=%s qty=%s", order_id, worker_id, qty)
        return order

    async def unclaim(self, *, order_id: str, worker_id: str, qty: int) -> Dict[str, Any]:
        self._validate_qty(qty, action="Unclaim")
        order = await self.orders.inc_unclaim(order_id=order_id, worker_id=worker_id, qty=qty)
        if not order:
            log.warning("Unclaim failed | insufficient claimed | order_id=%s worker=%s qty=%s", order_id, worker_id, qty)
            raise ValueError("You don't have that many claimed items")
        order = await self._post_unclaim(order=order, worker_id=worker_id)
        log.info("Unclaim success | order_id=%s worker=%s qty=%s", order_id, worker_id, qty)
        return order
    
    async def force_claim(self, *, order_id: str, worker_id: str, qty: int) -> Dict[str, Any]:
        self._validate_qty(qty, action="Force claim")
        order = await self.orders.inc_claim(order_id=order_id, worker_id=worker_id, qty=qty)
        if not order:
            log.warning("Force claim failed | insufficient qty or invalid state | order_id=%s worker=%s qty=%s", order_id, worker_id, qty)
            raise ValueError("Not enough claimable quantity")
        log.warning("Force claim success | order_id=%s worker=%s qty=%s", order_id, worker_id, qty)
        return order

    async def force_unclaim(self, *, order_id: str, worker_id: str, qty: int) -> Dict[str, Any]:
        self._validate_qty(qty, action="Force unclaim")
        order = await self.orders.inc_unclaim(order_id=order_id, worker_id=worker_id, qty=qty)
        if not order:
            log.warning("Force unclaim failed | insufficient claimed | order_id=%s worker=%s qty=%s", order_id, worker_id, qty)
            raise ValueError("Worker does not have that many claimed items")
        order = await self._post_unclaim(order=order, worker_id=worker_id)
        log.warning("Force unclaim success | order_id=%s worker=%s qty=%s", order_id, worker_id, qty)
        return order
