from __future__ import annotations

import pytest

from services.order_claim_math import (
    next_quota_quantity,
    quota_quantity_of,
    resolve_updated_quantity,
)


def test_set_replaces_total() -> None:
    assert resolve_updated_quantity(current=2000, mode="set", amount=500) == 500


def test_add_increases_total() -> None:
    assert resolve_updated_quantity(current=2000, mode="add", amount=500) == 2500


def test_reduce_decreases_total() -> None:
    assert resolve_updated_quantity(current=2000, mode="reduce", amount=500) == 1500


def test_amount_must_be_positive() -> None:
    with pytest.raises(ValueError, match="Quantity must be > 0"):
        resolve_updated_quantity(current=2000, mode="add", amount=0)


def test_quota_falls_back_to_item_quantity() -> None:
    assert quota_quantity_of({"item_quantity": 2000}) == 2000
    assert quota_quantity_of({"item_quantity": 20000, "quota_quantity": 2000}) == 2000


def test_override_increase_keeps_quota() -> None:
    assert next_quota_quantity(
        current_quota=2000,
        new_item_qty=20000,
        item_delta=18000,
        override=True,
    ) == 2000


def test_override_reduce_clamps_quota() -> None:
    assert next_quota_quantity(
        current_quota=2000,
        new_item_qty=500,
        item_delta=-1500,
        override=True,
    ) == 500


def test_regular_increase_uses_quota() -> None:
    assert next_quota_quantity(
        current_quota=2000,
        new_item_qty=2500,
        item_delta=500,
        override=False,
    ) == 2500


def test_regular_reduce_clamps_quota() -> None:
    assert next_quota_quantity(
        current_quota=2000,
        new_item_qty=500,
        item_delta=-1500,
        override=False,
    ) == 500
