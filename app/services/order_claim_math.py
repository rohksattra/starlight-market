from __future__ import annotations

from app.domains.order_domain import OrderClaims


def min_quantity_for_update(claims: OrderClaims) -> int:
    return claims["order_claimed"] + claims["order_completed"] + claims["order_delivered"]


def quantity_delta_claimable(*, old_qty: int, new_qty: int, claims: OrderClaims) -> int:
    return claims["order_claimable"] + (new_qty - old_qty)
