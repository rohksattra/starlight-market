# app/services/transaction_service.py
from __future__ import annotations

import logging
from typing import Any, Dict, Literal
from uuid import uuid4

from core.config import WORKER_FEE_RATE
from app.domains.enums.order_status_enum import OrderStatus
from app.domains.enums.role_enum import ServerRole

from app.repositories.order_repo import OrderRepository
from app.repositories.transaction_repo import TransactionRepository
from app.repositories.worker_repo import WorkerRepository
from app.repositories.customer_repo import CustomerRepository
from app.repositories.item_repo import ItemRepository
from app.repositories.statistic_repo import StatisticRepository


IncomeTarget = Literal["worker", "customer"]
log = logging.getLogger("services.income_service")


class TransactionService:
    def __init__(self) -> None:
        self.customers = CustomerRepository()
        self.items = ItemRepository()
        self.orders = OrderRepository()
        self.statistics = StatisticRepository()
        self.transactions = TransactionRepository()
        self.workers = WorkerRepository()

    def _validate_quantity(self, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("Quantity must be > 0")

    async def record_income(self, *, channel_id: str, target: IncomeTarget, user_id: str, quantity: int) -> Dict[str, Any]:
        self._validate_quantity(quantity)
        order = await self.orders.get_by_channel_id(channel_id)
        if not order:
            log.warning("Record income failed | order not found | channel=%s", channel_id)
            raise ValueError("Order not found")
        transaction_id = str(uuid4())
        if target == "worker":
            updated = await self.orders.inc_complete_by_worker(order_id=order["order_id"], worker_id=user_id, qty=quantity)
            if not updated:
                log.warning("Income(worker) denied | order=%s worker=%s qty=%s", order["order_id"], user_id, quantity)
                raise ValueError("Cannot complete more than claimed")
            if updated.get("worker_claims", {}).get(user_id, 0) <= 0:
                await self.orders.unset_worker_claim(order["order_id"], user_id)
            raw_income = order["item_price"] * quantity
            worker_income = int(raw_income * WORKER_FEE_RATE)
            ok = await self.transactions.create_transaction({
                "transaction_id": transaction_id,
                "order_id": order["order_id"],
                "user_id": user_id,
                "user_role": ServerRole.WORKER,
                "item_id": order["item_id"],
                "item_quantity": quantity,
                "total_price": worker_income,
            })
            if not ok:
                log.info("Income(worker) duplicate ignored | tx=%s", transaction_id)
                return {"order": updated, "target": "worker", "finished": False}
            await self.workers.ensure_worker(user_id)
            await self.workers.inc_worker_income(worker_id=user_id, finished_item_inc=quantity, income_inc=worker_income)
            await self.statistics.inc_worker_income(amount=worker_income)
            claims = updated["order_claims"]
            finished = (claims["order_completed"] + claims["order_delivered"] >= updated["item_quantity"])
            if finished and updated["order_status"] != OrderStatus.COMPLETED:
                updated = await self.orders.update_fields(order["order_id"], {"order_status": OrderStatus.COMPLETED})
            log.info(
                "Income(worker) | order=%s worker=%s qty=%s income=%s finished=%s", order["order_id"], user_id, quantity, worker_income, finished,
            )
            return {"order": updated, "target": "worker", "finished": finished}
        if user_id != order["customer_id"]:
            log.warning("Income(customer) denied | order=%s user=%s", order["order_id"], user_id)
            raise ValueError("This customer does not own the order")
        updated = await self.orders.inc_deliver_to_customer(order_id=order["order_id"], qty=quantity)
        if not updated:
            log.warning("Income(customer) denied | order=%s qty=%s", order["order_id"], quantity)
            raise ValueError("Quantity exceeds completed items")
        total_price = order["item_price"] * quantity
        ok = await self.transactions.create_transaction({
            "transaction_id": transaction_id,
            "order_id": order["order_id"],
            "user_id": user_id,
            "user_role": ServerRole.CUSTOMER,
            "item_id": order["item_id"],
            "item_quantity": quantity,
            "total_price": total_price,
        })
        if not ok:
            log.info("Income(customer) duplicate ignored | tx=%s", transaction_id)
            return {"order": updated, "target": "customer", "delivered": False}
        await self.customers.ensure_customer(user_id)
        await self.customers.inc_customer_spent(customer_id=user_id, amount=total_price)
        if not order.get("is_custom"):
            await self.items.inc_item_sold(item_id=order["item_id"], qty=quantity)
        await self.statistics.inc_customer_spent(amount=total_price)
        delivered = (updated["order_claims"]["order_delivered"] >= updated["item_quantity"])
        if delivered and updated["order_status"] != OrderStatus.DELIVERED:
            updated = await self.orders.update_fields(order["order_id"], {"order_status": OrderStatus.DELIVERED})
        log.info(
            "Income(customer) | order=%s customer=%s qty=%s spent=%s delivered=%s", order["order_id"], user_id, quantity, total_price, delivered,
        )
        return {"order": updated, "target": "customer", "delivered": delivered}
