# app/domains/statistic_domain.py
from __future__ import annotations

from typing import TypedDict
from datetime import datetime


class OrderStatistics(TypedDict):
    total_customer_order: int
    total_finished_order: int
    total_canceled_order: int


class GoldStatistics(TypedDict):
    total_worker_income: int
    total_customer_spent: int


class GlobalStatistics(TypedDict):
    orders: OrderStatistics
    gold: GoldStatistics
    updated_at: datetime
