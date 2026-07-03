from __future__ import annotations

from dataclasses import dataclass

from core.tier_limits import (
    customer_limits_for_spent,
    donor_limits_for_total,
    worker_limits_for_income,
)
from app.repositories.order_repo import OrderRepository
from app.repositories.user_repo import UserRepository


@dataclass(frozen=True)
class ProfileLimitInfo:
    coupon_remaining: int
    coupon_max: int
    claim_order_remaining: int
    claim_order_max: int
    claim_capacity_remaining: int | None
    claim_capacity_max: int | None
    active_order_remaining: int
    active_order_max: int
    order_capacity_remaining: int | None
    order_capacity_max: int | None


class TierLimitsService:
    def __init__(self) -> None:
        self.users = UserRepository()
        self.orders = OrderRepository()

    async def validate_customer_order(self, *, customer_id: str, quantity: int) -> None:
        user = await self.users.get_user(customer_id) or {}
        spent = int(user.get("total_customer_spent", 0) or 0)
        limits = customer_limits_for_spent(spent)

        active_count = await self.orders.count_active_by_customer(customer_id)
        if active_count >= limits.max_active_orders:
            raise ValueError(
                f"Active order limit reached (**{active_count}/{limits.max_active_orders}**)"
            )

        if limits.order_capacity is not None:
            active_qty = await self.orders.sum_active_quantity_by_customer(customer_id)
            projected = active_qty + quantity
            if projected > limits.order_capacity:
                raise ValueError(
                    f"Order capacity limit reached (**{projected:,}/{limits.order_capacity:,}**)"
                )

    async def validate_worker_claim(
        self,
        *,
        worker_id: str,
        order_id: str,
        quantity: int,
    ) -> None:
        order = await self.orders.get_by_id(order_id)
        if not order:
            raise ValueError("Order not found")

        user = await self.users.get_user(worker_id) or {}
        income = int(user.get("total_worker_income", 0) or 0)
        limits = worker_limits_for_income(income)

        already_on_order = int(order.get("worker_claims", {}).get(worker_id, 0) or 0) > 0
        if not already_on_order:
            active_count = await self.orders.count_active_by_worker(worker_id)
            if active_count >= limits.max_claim_orders:
                raise ValueError(
                    f"Claim order limit reached (**{active_count}/{limits.max_claim_orders}**)"
                )

        if limits.claim_capacity is not None:
            active_qty = await self.orders.sum_active_claim_quantity_by_worker(worker_id)
            projected = active_qty + quantity
            if projected > limits.claim_capacity:
                raise ValueError(
                    f"Claim capacity limit reached (**{projected:,}/{limits.claim_capacity:,}**)"
                )

    async def get_profile_limits(self, *, user_id: str) -> ProfileLimitInfo:
        user = await self.users.get_user(user_id) or {}
        donation = int(user.get("donation_given", 0) or 0)
        income = int(user.get("total_worker_income", 0) or 0)
        spent = int(user.get("total_customer_spent", 0) or 0)

        donor_limits = donor_limits_for_total(donation)
        worker_limits = worker_limits_for_income(income)
        customer_limits = customer_limits_for_spent(spent)

        coupons_used = await self.users.get_coupons_used(user_id)
        active_claim_orders = await self.orders.count_active_by_worker(user_id)
        active_claim_qty = await self.orders.sum_active_claim_quantity_by_worker(user_id)
        active_orders = await self.orders.count_active_by_customer(user_id)
        active_order_qty = await self.orders.sum_active_quantity_by_customer(user_id)

        claim_capacity_remaining: int | None = None
        if worker_limits.claim_capacity is not None:
            claim_capacity_remaining = max(0, worker_limits.claim_capacity - active_claim_qty)

        order_capacity_remaining: int | None = None
        if customer_limits.order_capacity is not None:
            order_capacity_remaining = max(0, customer_limits.order_capacity - active_order_qty)

        return ProfileLimitInfo(
            coupon_remaining=max(0, donor_limits.max_coupons - coupons_used),
            coupon_max=donor_limits.max_coupons,
            claim_order_remaining=max(0, worker_limits.max_claim_orders - active_claim_orders),
            claim_order_max=worker_limits.max_claim_orders,
            claim_capacity_remaining=claim_capacity_remaining,
            claim_capacity_max=worker_limits.claim_capacity,
            active_order_remaining=max(0, customer_limits.max_active_orders - active_orders),
            active_order_max=customer_limits.max_active_orders,
            order_capacity_remaining=order_capacity_remaining,
            order_capacity_max=customer_limits.order_capacity,
        )
