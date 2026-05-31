from __future__ import annotations

from typing import TypedDict, Dict
from datetime import datetime

from app.domains.enums.order_status_enum import OrderStatus


class OrderClaims(TypedDict):
    order_delivered: int
    order_completed: int
    order_claimed: int
    order_claimable: int


class OrderCreate(TypedDict):
    order_id: str
    order_number: int
    channel_id: str
    embed_message_id: str
    customer_id: str
    item_id: str
    item_name: str
    item_price: int
    item_quantity: int
    item_image: str
    item_category: str
    is_custom: bool
    worker_claims: Dict[str, int]
    order_claims: OrderClaims
    order_status: OrderStatus


class Order(OrderCreate):
    created_at: datetime
    updated_at: datetime
