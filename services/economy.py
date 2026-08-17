"""Service for economy: income, donation, manual paid/spent."""
from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import uuid4

from core.constants import DONOR_COUPON_DISCOUNT_RATE
from core.tenant import GameContext
from database.donations import DonationRepo
from database.items import ItemRepo
from database.orders import OrderRepo
from database.statistics import StatisticRepo
from database.transaction_docs import TransactionRepo
from database.transactions import run_transaction
from database.users import UserRepo
from models.enums import OrderStatus, ServerRole
from models.order import Order

IncomeTarget = Literal["worker", "customer"]
log = logging.getLogger("services.economy")


class EconomyService:
    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self.users = UserRepo(ctx.db_name)
        self.items = ItemRepo(ctx.db_name)
        self.orders = OrderRepo(ctx.db_name)
        self.statistics = StatisticRepo(ctx.db_name)
        self.transactions = TransactionRepo(ctx.db_name)
        self.donations = DonationRepo(ctx.db_name)

    def _worker_keep_rate(self) -> float:
        return 1.0 - float(self.ctx.economy.worker_fee_rate)

    def _validate_quantity(self, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("Quantity must be > 0")

    async def record_income(
        self,
        *,
        channel_id: str,
        target: IncomeTarget,
        user_id: str,
        quantity: int,
    ) -> dict[str, Any]:
        self._validate_quantity(quantity)
        order = await self.orders.get_by_channel_id(channel_id)
        if not order:
            log.warning("Record income failed | order not found | channel=%s", channel_id)
            raise ValueError("Order not found")

        async def work(session: object) -> dict[str, Any]:
            if target == "worker":
                return await self._record_worker_income(
                    session,
                    order=order,
                    user_id=user_id,
                    quantity=quantity,
                )
            return await self._record_customer_income(
                session,
                order=order,
                user_id=user_id,
                quantity=quantity,
            )

        return await run_transaction(work)

    async def _record_worker_income(
        self,
        session: object,
        *,
        order: Order,
        user_id: str,
        quantity: int,
    ) -> dict[str, Any]:
        transaction_id = str(uuid4())
        updated = await self.orders.inc_complete_by_worker(
            order_id=order["order_id"],
            worker_id=user_id,
            qty=quantity,
            session=session,
        )
        if not updated:
            log.warning(
                "Income(worker) denied | order=%s worker=%s qty=%s",
                order["order_id"],
                user_id,
                quantity,
            )
            raise ValueError("Cannot complete more than claimed")

        if updated.get("worker_claims", {}).get(user_id, 0) <= 0:
            updated = await self.orders.unset_worker_claim(
                order["order_id"],
                user_id,
                session=session,
            ) or updated

        price = updated["item_price"]
        raw_income = price * quantity
        worker_income = int(raw_income * self._worker_keep_rate())

        ok = await self.transactions.create_transaction(
            {
                "transaction_id": transaction_id,
                "order_id": order["order_id"],
                "user_id": user_id,
                "user_role": ServerRole.WORKER,
                "item_id": updated["item_id"],
                "item_quantity": quantity,
                "total_price": worker_income,
            },
            session=session,
        )
        if not ok:
            log.info("Income(worker) duplicate ignored | tx=%s", transaction_id)
            raise ValueError("Duplicate transaction")

        await self.users.ensure_user(user_id, session=session)
        await self.users.inc_worker_income(
            user_id=user_id,
            finished_item_inc=quantity,
            income_inc=worker_income,
            session=session,
        )
        await self.statistics.inc_worker_income(amount=worker_income, session=session)

        claims = updated["order_claims"]
        finished = (
            claims["order_completed"] + claims["order_delivered"]
            >= updated["item_quantity"]
        )
        if finished and updated["order_status"] != OrderStatus.COMPLETED:
            updated = await self.orders.update_fields(
                order["order_id"],
                {"order_status": OrderStatus.COMPLETED},
                session=session,
            ) or updated

        log.info(
            "Income(worker) | order=%s worker=%s qty=%s income=%s finished=%s",
            order["order_id"],
            user_id,
            quantity,
            worker_income,
            finished,
        )
        return {"order": updated, "target": "worker", "finished": finished}

    async def _record_customer_income(
        self,
        session: object,
        *,
        order: Order,
        user_id: str,
        quantity: int,
    ) -> dict[str, Any]:
        if user_id != order["customer_id"]:
            log.warning("Income(customer) denied | order=%s user=%s", order["order_id"], user_id)
            raise ValueError("This customer does not own the order")

        transaction_id = str(uuid4())
        updated = await self.orders.inc_deliver_to_customer(
            order_id=order["order_id"],
            qty=quantity,
            session=session,
        )
        if not updated:
            log.warning(
                "Income(customer) denied | order=%s qty=%s",
                order["order_id"],
                quantity,
            )
            raise ValueError("Quantity exceeds completed items")

        price = updated["item_price"]
        total_price = price * quantity
        if updated.get("coupon_applied"):
            total_price = int(total_price * (1 - DONOR_COUPON_DISCOUNT_RATE))

        ok = await self.transactions.create_transaction(
            {
                "transaction_id": transaction_id,
                "order_id": order["order_id"],
                "user_id": user_id,
                "user_role": ServerRole.CUSTOMER,
                "item_id": updated["item_id"],
                "item_quantity": quantity,
                "total_price": total_price,
            },
            session=session,
        )
        if not ok:
            log.info("Income(customer) duplicate ignored | tx=%s", transaction_id)
            raise ValueError("Duplicate transaction")

        await self.users.ensure_user(user_id, session=session)
        await self.users.inc_customer_spent(
            user_id=user_id,
            amount=total_price,
            session=session,
        )
        if not updated.get("is_custom"):
            await self.items.inc_item_sold(
                item_id=updated["item_id"],
                qty=quantity,
                session=session,
            )
        await self.statistics.inc_customer_spent(amount=total_price, session=session)

        delivered = (
            updated["order_claims"]["order_delivered"] >= updated["item_quantity"]
        )
        if delivered and updated["order_status"] != OrderStatus.DELIVERED:
            updated = await self.orders.update_fields(
                order["order_id"],
                {"order_status": OrderStatus.DELIVERED},
                session=session,
            ) or updated

        log.info(
            "Income(customer) | order=%s customer=%s qty=%s spent=%s delivered=%s",
            order["order_id"],
            user_id,
            quantity,
            total_price,
            delivered,
        )
        return {"order": updated, "target": "customer", "delivered": delivered}

    async def record_donation(self, *, user_id: str, gold: int) -> dict[str, Any]:
        if gold <= 0:
            raise ValueError("Gold must be > 0")
        await self.users.ensure_user(user_id)
        await self.users.inc_donation_given(user_id=user_id, amount=gold)
        await self.donations.create(user_id=user_id, gold=gold)
        log.info("Donation recorded | user=%s gold=%s", user_id, gold)
        return await self.users.get_user(user_id) or {}

    async def paid_worker(
        self,
        *,
        user_id: str,
        item_id: str,
        quantity: int,
    ) -> dict[str, Any]:
        self._validate_quantity(quantity)

        item = await self.items.get_by_id(item_id)
        if not item:
            raise ValueError("Item not found")

        price = int(item["item_price"])
        raw_income = price * quantity
        worker_income = int(raw_income * self._worker_keep_rate())

        await self.users.ensure_user(user_id)
        await self.users.inc_worker_income(
            user_id=user_id,
            finished_item_inc=quantity,
            income_inc=worker_income,
        )
        await self.statistics.inc_worker_income(amount=worker_income)
        await self.transactions.create_transaction(
            {
                "transaction_id": str(uuid4()),
                "order_id": "",
                "user_id": user_id,
                "user_role": ServerRole.WORKER,
                "item_id": item_id,
                "item_quantity": quantity,
                "total_price": worker_income,
            }
        )

        log.info(
            "Manual paid | user=%s item=%s qty=%s income=%s",
            user_id,
            item_id,
            quantity,
            worker_income,
        )
        return {
            "user_id": user_id,
            "item_name": item["item_name"],
            "item_price": price,
            "quantity": quantity,
            "income": worker_income,
        }

    async def spent_customer(
        self,
        *,
        user_id: str,
        item_id: str,
        quantity: int,
    ) -> dict[str, Any]:
        self._validate_quantity(quantity)

        item = await self.items.get_by_id(item_id)
        if not item:
            raise ValueError("Item not found")

        price = int(item["item_price"])
        total_price = price * quantity

        await self.users.ensure_user(user_id)
        await self.users.inc_customer_spent(user_id=user_id, amount=total_price)
        await self.items.inc_item_sold(item_id=item_id, qty=quantity)
        await self.statistics.inc_customer_spent(amount=total_price)
        await self.transactions.create_transaction(
            {
                "transaction_id": str(uuid4()),
                "order_id": "",
                "user_id": user_id,
                "user_role": ServerRole.CUSTOMER,
                "item_id": item_id,
                "item_quantity": quantity,
                "total_price": total_price,
            }
        )

        log.info(
            "Manual spent | user=%s item=%s qty=%s spent=%s",
            user_id,
            item_id,
            quantity,
            total_price,
        )
        return {
            "user_id": user_id,
            "item_name": item["item_name"],
            "item_price": price,
            "quantity": quantity,
            "spent": total_price,
        }
