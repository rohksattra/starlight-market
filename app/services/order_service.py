from __future__ import annotations

import logging
from uuid import uuid4

from app.domains.enums.order_status_enum import OrderStatus
from db.mongo_transaction import run_transaction
from app.domains.order_domain import Order, OrderCreate
from app.services.order_claim_math import min_quantity_for_update, quantity_delta_claimable
from app.repositories.item_repo import ItemRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.statistic_repo import StatisticRepository
from app.repositories.user_repo import UserRepository


OrderData = Order
OrderDraft = OrderCreate
log = logging.getLogger("services.order_service")

MAX_ACTIVE_ORDERS = 12


class OrderService:
    def __init__(self) -> None:
        self.users = UserRepository()
        self.items = ItemRepository()
        self.orders = OrderRepository()
        self.statistics = StatisticRepository()

    async def _validate_active_order(self, customer_id: str) -> None:
        active = await self.orders.count_active_by_customer(customer_id)

        if active >= MAX_ACTIVE_ORDERS:
            log.warning(
                "Create order denied | active_limit | customer=%s active=%s",
                customer_id,
                active,
            )
            raise ValueError("Active order limit reached")

    async def get_by_channel_id(self, channel_id: str) -> OrderData | None:
        return await self.orders.get_by_channel_id(channel_id)

    async def get_active_by_worker(self, worker_id: str) -> list[OrderData]:
        return await self.orders.get_active_by_worker(worker_id)

    async def get_active_by_customer(self, customer_id: str) -> list[OrderData]:
        return await self.orders.get_active_by_customer(customer_id)

    async def count_active_by_worker(self, worker_id: str) -> int:
        return await self.orders.count_active_by_worker(worker_id)

    async def create_order(
        self,
        *,
        customer_id: str,
        item_id: str,
        quantity: int,
    ) -> OrderData:
        if quantity <= 0:
            raise ValueError("Quantity must be > 0")

        await self._validate_active_order(customer_id)

        item = await self.items.get_by_id(item_id)
        if not item:
            log.warning(
                "Create order failed | item not found | item_id=%s customer=%s",
                item_id,
                customer_id,
            )
            raise ValueError("Item not found")

        order_number = await self.orders.next_order_number()
        order_id = str(uuid4())

        order: OrderDraft = {
            "order_id": order_id,
            "order_number": order_number,
            "channel_id": "",
            "embed_message_id": "",
            "customer_id": customer_id,
            "item_id": item["item_id"],
            "item_name": item["item_name"],
            "item_price": item["item_price"],
            "item_image": item.get("item_image", ""),
            "item_category": item.get("item_category", ""),
            "item_quantity": quantity,
            "is_custom": False,
            "worker_claims": {},
            "order_claims": {
                "order_delivered": 0,
                "order_completed": 0,
                "order_claimed": 0,
                "order_claimable": quantity,
            },
            "order_status": OrderStatus.NEW,
        }

        await self._persist_new_order(order, customer_id)

        log.info(
            "Order created | order_id=%s order_number=%s customer=%s item_id=%s qty=%s",
            order_id,
            order_number,
            customer_id,
            item_id,
            quantity,
        )

        return order

    async def create_custom_order(
        self,
        *,
        customer_id: str,
        item_name: str,
        item_price: int,
        item_quantity: int,
    ) -> OrderData:
        if item_quantity <= 0:
            raise ValueError("Quantity must be > 0")

        if item_price <= 0:
            raise ValueError("Price must be > 0")

        await self._validate_active_order(customer_id)

        order_number = await self.orders.next_order_number()
        order_id = str(uuid4())

        order: OrderDraft = {
            "order_id": order_id,
            "order_number": order_number,
            "channel_id": "",
            "embed_message_id": "",
            "customer_id": customer_id,
            "item_id": str(uuid4()),
            "item_name": item_name,
            "item_price": item_price,
            "item_image": "",
            "item_category": "",
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

        await self._persist_new_order(order, customer_id)

        log.info(
            "Custom order created | order_id=%s order_number=%s customer=%s qty=%s price=%s",
            order_id,
            order_number,
            customer_id,
            item_quantity,
            item_price,
        )

        return order

    async def _persist_new_order(self, order: OrderDraft, customer_id: str) -> None:
        async def work(session: object) -> None:
            await self.orders.create_order(order, session=session)
            await self.users.ensure_user(customer_id, session=session)
            await self.users.inc_customer_order(user_id=customer_id, session=session)
            await self.statistics.inc_customer_order(session=session)

        await run_transaction(work)

    async def update_price(
        self,
        *,
        order: OrderData,
        new_price: int,
    ) -> OrderData:
        if new_price <= 0:
            raise ValueError("Price must be > 0")

        updated = await self.orders.update_fields(
            order_id=order["order_id"],
            fields={"item_price": new_price},
        )

        if not updated:
            raise ValueError("Order not found")

        log.info(
            "Order price updated | order_id=%s new_price=%s",
            order["order_id"],
            new_price,
        )

        return updated

    async def update_quantity(
        self,
        *,
        order: OrderData,
        new_quantity: int,
    ) -> OrderData:
        if order["order_status"] in {
            OrderStatus.COMPLETED,
            OrderStatus.DELIVERED,
            OrderStatus.CLOSED,
        }:
            raise ValueError("Cannot update quantity for finalized orders.")

        if new_quantity <= 0:
            raise ValueError("Quantity must be > 0")

        claims = order["order_claims"]
        min_required = min_quantity_for_update(claims)

        if new_quantity < min_required:
            log.warning(
                "Update qty denied | below claimed | order=%s new=%s min=%s",
                order["order_id"],
                new_quantity,
                min_required,
            )
            raise ValueError(f"Quantity must be ≥ {min_required}")

        updated = await self.orders.update_fields(
            order_id=order["order_id"],
            fields={
                "item_quantity": new_quantity,
                "order_claims.order_claimable": quantity_delta_claimable(
                    old_qty=order["item_quantity"],
                    new_qty=new_quantity,
                    claims=claims,
                ),
            },
        )

        if not updated:
            raise ValueError("Order not found")

        claims_updated = updated["order_claims"]

        if (
            updated["order_status"] == OrderStatus.CLAIMED
            and claims_updated["order_completed"] >= updated["item_quantity"]
        ):
            updated = await self.orders.update_fields(
                order["order_id"],
                {"order_status": OrderStatus.COMPLETED},
            )

            if not updated:
                raise ValueError("Order not found")

        log.info(
            "Order quantity updated | order_id=%s new_qty=%s",
            order["order_id"],
            new_quantity,
        )

        return updated

    async def update_customer(self, *, order: OrderData, new_customer_id: str) -> OrderData:
        old_customer_id = order["customer_id"]
        if old_customer_id == new_customer_id:
            raise ValueError("New customer is the same as the current customer.")

        if order["order_status"] in {OrderStatus.CLOSED, OrderStatus.CANCELED}:
            raise ValueError("Cannot change customer for closed or canceled orders.")

        claimed_qty = int(order["worker_claims"].get(new_customer_id, 0))
        if claimed_qty > 0:
            raise ValueError("The new customer already has claims on this order.")

        if order["order_status"] in {
            OrderStatus.NEW,
            OrderStatus.CLAIMED,
            OrderStatus.COMPLETED,
            OrderStatus.DELIVERED,
        }:
            await self._validate_active_order(new_customer_id)

        async def work(session: object) -> OrderData:
            updated = await self.orders.update_fields(
                order_id=order["order_id"],
                fields={"customer_id": new_customer_id},
                session=session,
            )
            if not updated:
                raise ValueError("Order not found")
            await self.users.transfer_customer_order_count(
                from_user_id=old_customer_id,
                to_user_id=new_customer_id,
                session=session,
            )
            return updated

        updated = await run_transaction(work)

        log.info(
            "Order customer updated | order_id=%s old=%s new=%s",
            order["order_id"],
            old_customer_id,
            new_customer_id,
        )

        return updated

    async def close_order(self, *, order: OrderData) -> None:
        if order["order_status"] != OrderStatus.DELIVERED:
            raise ValueError("Only delivered orders can be closed")

        if not await self.orders.update_fields(
            order_id=order["order_id"],
            fields={"order_status": OrderStatus.CLOSED},
        ):
            raise ValueError("Order not found")

        await self.statistics.inc_finished_order()

        log.info("Order closed | order_id=%s", order["order_id"])

    async def cancel_order(self, *, order: OrderData) -> None:
        if not await self.orders.update_fields(
            order_id=order["order_id"],
            fields={"order_status": OrderStatus.CANCELED},
        ):
            raise ValueError("Order not found")

        await self.statistics.inc_canceled_order()

        log.warning("Order canceled | order_id=%s", order["order_id"])

    async def set_channel_and_message(
        self,
        *,
        order_id: str,
        channel_id: str,
        message_id: int,
    ) -> None:
        await self.orders.set_channel(order_id, channel_id)
        await self.orders.set_embed_message(order_id, str(message_id))

        log.info(
            "Order channel & embed set | order_id=%s channel=%s message=%s",
            order_id,
            channel_id,
            message_id,
        )