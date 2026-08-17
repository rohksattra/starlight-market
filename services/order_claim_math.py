"""Helpers for order quantity updates."""
from __future__ import annotations

from typing import Literal, Mapping

QuantityUpdateMode = Literal["set", "add", "reduce"]


def resolve_updated_quantity(*, current: int, mode: QuantityUpdateMode, amount: int) -> int:
    if amount <= 0:
        raise ValueError("Quantity must be > 0")
    if mode == "set":
        return amount
    if mode == "add":
        return current + amount
    if mode == "reduce":
        return current - amount
    raise ValueError("Invalid quantity mode")


def min_quantity_for_update(claims: Mapping[str, int]) -> int:
    return int(claims["order_claimed"]) + int(claims["order_completed"]) + int(claims["order_delivered"])


def quantity_delta_claimable(*, old_qty: int, new_qty: int, claims: Mapping[str, int]) -> int:
    return int(claims["order_claimable"]) + (new_qty - old_qty)
