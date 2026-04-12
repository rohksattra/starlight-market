# app/domains/item_domain.py
from __future__ import annotations

from typing import TypedDict
from datetime import datetime


class Item(TypedDict):
    item_id: str
    item_category: str
    item_name: str
    item_price: int
    item_sold: int
    item_image: str
    item_emoji: str
    updated_at: datetime | None
