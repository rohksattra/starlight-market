"""Service for profile: fetch user data, compute tier progress."""
from __future__ import annotations

from typing import Any

from core.tenant import GameContext
from database.orders import OrderRepo
from database.users import UserRepo
from services.tier_limits import TierLimitsService


class ProfileService:
    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self.users = UserRepo(ctx.db_name)
        self.orders = OrderRepo(ctx.db_name)
        self.tier_limits = TierLimitsService(ctx)

    async def get_or_ensure_user(self, user_id: str) -> dict[str, Any]:
        doc = await self.users.get_user(user_id)
        if not doc:
            await self.users.ensure_user(user_id)
            doc = await self.users.get_user(user_id) or {}
        return doc

    async def get_profile_data(self, *, user_id: str) -> dict[str, Any]:
        worker_orders: list[str] = []
        active_worker = await self.orders.get_active_by_worker(user_id)
        for o in active_worker:
            qty = o.get("worker_claims", {}).get(user_id, 0)
            if qty > 0 and o.get("channel_id"):
                worker_orders.append(f"- <#{o['channel_id']}> x***{qty:,}***")

        user = await self.users.get_user(user_id)
        total_income = user["total_worker_income"] if user else 0
        worker_rank = await self.users.get_rank_worker(user_id) if total_income > 0 else None

        rating_count = user["count_worker_rating"] if user else 0
        rating_total = user["total_worker_star"] if user else 0
        rating_avg = (rating_total / rating_count) if rating_count else 0.0

        customer_orders: list[str] = []
        active_customer = await self.orders.get_active_by_customer(user_id)
        for o in active_customer:
            if o.get("channel_id"):
                customer_orders.append(f"- <#{o['channel_id']}>")

        total_spent = user["total_customer_spent"] if user else 0
        customer_rank = await self.users.get_rank_customer(user_id) if total_spent > 0 else None

        donation_given = int(user.get("donation_given", 0) or 0) if user else 0
        donor_rank = await self.users.get_rank_donor(user_id) if donation_given > 0 else None

        limits = await self.tier_limits.get_profile_limits(user_id=user_id)
        return {
            "worker_orders": worker_orders,
            "customer_orders": customer_orders,
            "worker_rank": worker_rank,
            "customer_rank": customer_rank,
            "donor_rank": donor_rank,
            "total_income": total_income,
            "total_spent": total_spent,
            "donation_given": donation_given,
            "worker_rating_avg": round(rating_avg, 2),
            "worker_rating_count": rating_count,
            "limits": limits,
        }
