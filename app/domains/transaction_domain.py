# app/domains/transaction_domain.py
from __future__ import annotations

from typing import TypedDict
from datetime import datetime

from app.domains.enums.role_enum import USER_ROLE


class Transaction(TypedDict):
    transaction_id: str
    created_at: datetime
    order_id: str
    user_id: str
    user_role: USER_ROLE
    item_id: str
    item_quantity: int
    total_price: int
