from __future__ import annotations

from datetime import datetime
from typing import TypedDict


class User(TypedDict):
    user_id: str
    donation_given: int
    total_customer_order: int
    total_customer_spent: int
    total_worker_finished_item: int
    total_worker_income: int
    count_worker_rating: int
    total_worker_star: int
    starlight_points: int
    counting_score: int
    wordchain_score: int
    trivia_score: int
    guess_score: int
    treasure_score: int
    boss_score: int
    reaction_score: int
    scramble_score: int
    daily_score: int
    monster_score: int
    coupons_used_month: int
    coupons_used_count: int
    updated_at: datetime
