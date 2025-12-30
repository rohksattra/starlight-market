# app/services/profile_service.py
from __future__ import annotations
from typing import List, Dict, Any

from app.repositories.order_repo import OrderRepository
from app.repositories.worker_repo import WorkerRepository
from app.repositories.customer_repo import CustomerRepository


class ProfileService:
    def __init__(self) -> None:
        self.customers = CustomerRepository()
        self.orders = OrderRepository()
        self.workers = WorkerRepository()

    async def get_profile_data(self, *, user_id: str) -> Dict[str, Any]:
        worker_orders: List[str] = []
        active_worker = await self.orders.get_active_by_worker(user_id)
        for o in active_worker:
            qty = o.get("worker_claims", {}).get(user_id, 0)
            if qty > 0 and o.get("channel_id"):
                worker_orders.append(f"- <#{o['channel_id']}> x***{qty:,}***")
        worker = await self.workers.get_worker(user_id)
        total_income = worker["total_worker_income"] if worker else 0
        worker_rank = await self.workers.get_rank_worker(user_id)
        rating_count = worker["count_worker_rating"] if worker else 0
        rating_total = worker["total_worker_star"] if worker else 0
        rating_avg = (rating_total / rating_count) if rating_count else 0.0

        customer_orders: List[str] = []
        active_customer = await self.orders.get_active_by_customer(user_id)
        for o in active_customer:
            if o.get("channel_id"):
                customer_orders.append(f"- <#{o['channel_id']}>")
        customer = await self.customers.get_customer(user_id)
        total_spent = customer["total_customer_spent"] if customer else 0
        customer_rank = await self.customers.get_rank_customer(user_id)
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
