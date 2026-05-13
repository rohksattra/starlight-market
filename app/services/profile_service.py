from __future__ import annotations
from typing import List, Dict, Any

from app.repositories.order_repo import OrderRepository
from app.repositories.user_repo import UserRepository


class ProfileService:
    def __init__(self) -> None:
        self.users = UserRepository()
        self.orders = OrderRepository()

    async def get_profile_data(self, *, user_id: str) -> Dict[str, Any]:
        worker_orders: List[str] = []
        active_worker = await self.orders.get_active_by_worker(user_id)
        for o in active_worker:
            qty = o.get("worker_claims", {}).get(user_id, 0)
            if qty > 0 and o.get("channel_id"):
                worker_orders.append(f"- <#{o['channel_id']}> x***{qty:,}***")
        user = await self.users.get_user(user_id)
        total_income = user["total_worker_income"] if user else 0
        if total_income > 0:
            worker_rank = await self.users.get_rank_worker(user_id)
        else:
            worker_rank = None
        rating_count = user["count_worker_rating"] if user else 0
        rating_total = user["total_worker_star"] if user else 0
        rating_avg = (rating_total / rating_count) if rating_count else 0.0
        customer_orders: List[str] = []
        active_customer = await self.orders.get_active_by_customer(user_id)
        for o in active_customer:
            if o.get("channel_id"):
                customer_orders.append(f"- <#{o['channel_id']}>")
        total_spent = user["total_customer_spent"] if user else 0
        if total_spent > 0:
            customer_rank = await self.users.get_rank_customer(user_id)
        else:
            customer_rank = None
        return {
            "worker_orders": worker_orders,
            "customer_orders": customer_orders,
            "worker_rank": worker_rank,
            "customer_rank": customer_rank,
            "total_income": total_income,
            "total_spent": total_spent,
            "worker_rating_avg": round(rating_avg, 2),
            "worker_rating_count": rating_count,
        }
