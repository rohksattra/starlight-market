# app/domains/customer_domain.py
from __future__ import annotations

from typing import TypedDict
from datetime import datetime


class Customer(TypedDict):
    customer_id: str
    total_customer_order: int
    total_customer_spent: int
    update_at: datetime | None
