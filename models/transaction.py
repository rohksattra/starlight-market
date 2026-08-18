from __future__ import annotations

from datetime import datetime
from typing import Literal, NotRequired, TypedDict

from models.enums import ServerRole

UserRole = Literal[ServerRole.WORKER, ServerRole.CUSTOMER]


class Transaction(TypedDict):
    transaction_id: str
    order_id: str
    user_id: str
    user_role: UserRole
    item_id: str
    item_quantity: int
    total_price: int
    created_at: NotRequired[datetime]
