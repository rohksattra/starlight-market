from __future__ import annotations

import pytest

from services.order_claim_math import resolve_updated_quantity


def test_set_replaces_total() -> None:
    assert resolve_updated_quantity(current=2000, mode="set", amount=500) == 500


def test_add_increases_total() -> None:
    assert resolve_updated_quantity(current=2000, mode="add", amount=500) == 2500


def test_reduce_decreases_total() -> None:
    assert resolve_updated_quantity(current=2000, mode="reduce", amount=500) == 1500


def test_amount_must_be_positive() -> None:
    with pytest.raises(ValueError, match="Quantity must be > 0"):
        resolve_updated_quantity(current=2000, mode="add", amount=0)
