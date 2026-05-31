from __future__ import annotations

from bson.int64 import Int64


def new_user_fields(*, user_id: str) -> dict:
    return {
        "user_id": user_id,
        "donation_given": Int64(0),
        "total_customer_order": Int64(0),
        "total_customer_spent": Int64(0),
        "total_worker_finished_item": Int64(0),
        "total_worker_income": Int64(0),
        "count_worker_rating": Int64(0),
        "total_worker_star": Int64(0),
        "starlight_points": Int64(0),
        "counting_score": Int64(0),
        "wordchain_score": Int64(0),
        "trivia_score": Int64(0),
        "guess_score": Int64(0),
        "treasure_score": Int64(0),
        "boss_score": Int64(0),
        "reaction_score": Int64(0),
        "scramble_score": Int64(0),
        "daily_score": Int64(0),
        "monster_score": Int64(0),
    }
