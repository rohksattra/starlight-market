from __future__ import annotations

from datetime import datetime
from typing import TypedDict


class Donation(TypedDict):
    donation_id: str
    user_id: str
    gold: int
    created_at: datetime
