"""Helpers for order quantity updates."""
from __future__ import annotations

from typing import Mapping


def min_quantity_for_update(claims: Mapping[str, int]) -> int:
    return int(claims["order_claimed"]) + int(claims["order_completed"]) + int(claims["order_delivered"])


def quantity_delta_claimable(*, old_qty: int, new_qty: int, claims: Mapping[str, int]) -> int:
    return int(claims["order_claimable"]) + (new_qty - old_qty)
