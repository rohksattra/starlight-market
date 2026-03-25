# app/services/order_service.py
from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import uuid4

from app.domains.enums.order_status_enum import OrderStatus
from app.repositories.customer_repo import CustomerRepository
from app.repositories.item_repo import ItemRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.statistic_repo import StatisticRepository


OrderData = Dict[str, Any]
log = logging.getLogger("services.order_service")

MAX_ACTIVE_ORDERS = 12


class OrderService:
    def __init__(self) -> None:
        self.customers = CustomerRepository()
        self.items = ItemRepository()
        self.orders = OrderRepository()
        self.statistics = StatisticRepository()

    async def _validate_active_order(self, customer_id: str) -> None:
        active = await self.orders.count_active_by_customer(customer_id)
        if active >= MAX_ACTIVE_ORDERS:
            log.warning("Create order denied | active_limit | customer=%s active=%s", customer_id, active)
            raise ValueError("Active order limit reached")

    async def get_by_channel_id(self, channel_id: str) -> OrderData | None:
        return await self.orders.get_by_channel_id(channel_id)

    async def get_active_by_worker(self, worker_id: str) -> list[OrderData]:
        return await self.orders.get_active_by_worker(worker_id)

    async def get_active_by_customer(self, customer_id: str) -> list[OrderData]:
        return await self.orders.get_active_by_customer(customer_id)

    async def count_active_by_worker(self, worker_id: str) -> int:
        return await self.orders.count_active_by_worker(worker_id)

    async def create_order(self, *, customer_id: str, item_id: str, quantity: int) -> OrderData:
        if quantity <= 0:
            raise ValueError("Quantity must be > 0")
        await self._validate_active_order(customer_id)
        item = await self.items.get_by_id(item_id)
        if not item:
            log.warning("Create order failed | item not found | item_id=%s customer=%s", item_id, customer_id)
            raise ValueError("Item not found")
        last_no = await self.orders.get_last_order_number()
        order_id = str(uuid4())
        order: OrderData = {
            "order_id": order_id,
            "order_number": last_no + 1,
            "channel_id": "",
            "embed_message_id": "",
            "customer_id": customer_id,
            "item_id": item["item_id"],
            "item_name": item["item_name"],
            "item_price": item["item_price"],
            "item_quantity": quantity,
            "worker_claims": {},
            "order_claims": {
                "order_delivered": 0,
                "order_completed": 0,
                "order_claimed": 0,
                "order_claimable": quantity,
            },
            "order_status": OrderStatus.NEW,
        }
        await self.orders.create_order(order)
        await self.customers.ensure_customer(customer_id)
        await self.customers.inc_customer_order(customer_id=customer_id)
        await self.statistics.inc_customer_order()
        log.info("Order created | order_id=%s customer=%s item_id=%s qty=%s", order_id, customer_id, item_id, quantity)
        return order

    async def create_custom_order(self, *, customer_id: str, item_name: str, item_price: int, item_quantity: int) -> OrderData:
        if item_quantity <= 0:
            raise ValueError("Quantity must be > 0")
        if item_price <= 0:
            raise ValueError("Price must be > 0")
        await self._validate_active_order(customer_id)
        last_no = await self.orders.get_last_order_number()
        order_id = str(uuid4())
        order: OrderData = {
            "order_id": order_id,
            "order_number": last_no + 1,
            "channel_id": "",
            "embed_message_id": "",
            "customer_id": customer_id,
            "item_id": str(uuid4()),
            "item_name": item_name,
            "item_price": item_price,
            "item_quantity": item_quantity,
            "is_custom": True,
            "worker_claims": {},
            "order_claims": {
                "order_delivered": 0,
                "order_completed": 0,
                "order_claimed": 0,
                "order_claimable": item_quantity,
            },
            "order_status": OrderStatus.NEW,
        }
        await self.orders.create_order(order)
        await self.customers.ensure_customer(customer_id)
        await self.customers.inc_customer_order(customer_id=customer_id)
        await self.statistics.inc_customer_order()
        log.info("Custom order created | order_id=%s customer=%s qty=%s price=%s", order_id, customer_id, item_quantity, item_price)
        return order

    async def update_price(self, *, order: OrderData, new_price: int) -> OrderData:
        if new_price <= 0:
            raise ValueError("Price must be > 0")
        updated = await self.orders.update_fields(order_id=order["order_id"], fields={"item_price": new_price})
        if not updated:
            raise ValueError("Order not found")
        log.info("Order price updated | order_id=%s new_price=%s", order["order_id"], new_price)
        return updated

    async def update_quantity(self, *, order: OrderData, new_quantity: int) -> OrderData:
        if order["order_status"] in {OrderStatus.COMPLETED, OrderStatus.DELIVERED, OrderStatus.CLOSED}:
            raise ValueError("Cannot update quantity for finalized orders.")
        if new_quantity <= 0:
            raise ValueError("Quantity must be > 0")
        claims = order["order_claims"]
        min_required = (claims["order_claimed"] + claims["order_completed"] + claims["order_delivered"])
        if new_quantity < min_required:
            log.warning("Update qty denied | below claimed | order=%s new=%s min=%s", order["order_id"], new_quantity, min_required)
            raise ValueError(f"Quantity must be ≥ {min_required}")
        diff = new_quantity - order["item_quantity"]
        updated = await self.orders.update_fields(
            order_id=order["order_id"],
            fields={"item_quantity": new_quantity, "order_claims.order_claimable": claims["order_claimable"] + diff},
        )
        if not updated:
            raise ValueError("Order not found")
        claims_updated = updated["order_claims"]
        if (updated["order_status"] == OrderStatus.CLAIMED and claims_updated["order_completed"] >= updated["item_quantity"]):
            updated = await self.orders.update_fields(order["order_id"], {"order_status": OrderStatus.COMPLETED})
            if not updated:
                raise ValueError("Order not found")
        log.info("Order quantity updated | order_id=%s new_qty=%s", order["order_id"], new_quantity)
        assert updated is not None
        return updated

    async def close_order(self, *, order: OrderData) -> None:
        if order["order_status"] != OrderStatus.DELIVERED:
            raise ValueError("Only delivered orders can be closed")
        if not await self.orders.update_fields(order_id=order["order_id"], fields={"order_status": OrderStatus.CLOSED}):
            raise ValueError("Order not found")
        await self.statistics.inc_finished_order()
        log.info("Order closed | order_id=%s", order["order_id"])

    async def cancel_order(self, *, order: OrderData) -> None:
        if not await self.orders.update_fields(order_id=order["order_id"], fields={"order_status": OrderStatus.CANCELED}):
            raise ValueError("Order not found")
        await self.statistics.inc_canceled_order()
        log.warning("Order canceled | order_id=%s", order["order_id"])

    async def set_channel_and_message(self, *, order_id: str, channel_id: str, message_id: int) -> None:
        await self.orders.set_channel(order_id, channel_id)
        await self.orders.set_embed_message(order_id, str(message_id))
        log.info("Order channel & embed set | order_id=%s channel=%s message=%s", order_id, channel_id, message_id)
