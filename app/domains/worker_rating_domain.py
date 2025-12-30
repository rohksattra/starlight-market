# app/domains/worker_rating_domain.py
from __future__ import annotations

from typing import TypedDict
from datetime import datetime


class WorkerRating(TypedDict):
    worker_rating_id: str
    transaction_id: str
    worker_id: str
    customer_id: str
    rating: int | None
    rated: bool
    created_at: datetime
    expired_at: datetime
    rated_at: datetime | None
