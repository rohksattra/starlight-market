from __future__ import annotations

import logging
from typing import Any, Dict

from core.config import WORKER_FEE_RATE

from app.repositories.user_repo import UserRepository
from app.repositories.item_repo import ItemRepository
from app.repositories.statistic_repo import StatisticRepository

log = logging.getLogger("services.manual_income_service")


class ManualIncomeService:
    def __init__(self) -> None:
        self.users = UserRepository()
        self.items = ItemRepository()
        self.statistics = StatisticRepository()

    def _validate_quantity(self, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("Quantity must be > 0")

    async def paid_worker(self, *, user_id: str, item_id: str, quantity: int) -> Dict[str, Any]:
        self._validate_quantity(quantity)

        item = await self.items.get_by_id(item_id)
        if not item:
            raise ValueError("Item not found")

        price = int(item["item_price"])
        raw_income = price * quantity
        worker_income = int(raw_income * WORKER_FEE_RATE)

        await self.users.ensure_user(user_id)
        await self.users.inc_worker_income(
            user_id=user_id,
            finished_item_inc=quantity,
            income_inc=worker_income,
        )

        await self.statistics.inc_worker_income(amount=worker_income)

        log.info("Manual paid | user=%s item=%s qty=%s income=%s", user_id, item_id, quantity, worker_income)

        return {"user_id": user_id, "item_name": item["item_name"], "item_price": price, "quantity": quantity, "income": worker_income}

    async def spent_customer(self, *, user_id: str, item_id: str, quantity: int) -> Dict[str, Any]:
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

        log.info("Manual spent | user=%s item=%s qty=%s spent=%s", user_id, item_id, quantity, total_price)

        return {"user_id": user_id, "item_name": item["item_name"], "item_price": price, "quantity": quantity, "spent": total_price}