# app/domains/worker_domain.py
from __future__ import annotations

from typing import TypedDict
from datetime import datetime


class Worker(TypedDict):
    worker_id: str
    total_finished_item: int
    total__worker_income: int
    count__worker_rating: int
    total_worker_star: int
    update_at: datetime | None
