# app/domains/order_domain.py
from __future__ import annotations

from typing import TypedDict, Dict
from datetime import datetime

from app.domains.enums.order_status_enum import OrderStatus


class OrderClaims(TypedDict):
    order_delivered: int
    order_completed: int
    order_claimed: int
    order_claimable: int


class Order(TypedDict):
    order_id: str
    created_at: datetime
    updated_at: datetime
    order_number: int
    channel_id: str
    embed_message_id: str
    customer_id: str
    item_id: str
    item_quantity: int
    worker_claims: Dict[str, int]
    order_claims: OrderClaims
    order_status: OrderStatus
