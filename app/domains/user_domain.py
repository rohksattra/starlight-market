from __future__ import annotations

from datetime import datetime
from typing import TypedDict


class User(TypedDict, total=False):
    user_id: str
    donation_given: int
    total_customer_order: int
    total_customer_spent: int
    total_worker_finished_item: int
    total_worker_income: int
    count_worker_rating: int
    total_worker_star: int
    counting_score: int
    updated_at: datetime

