from __future__ import annotations

import inspect

from database.indexes import ensure_indexes


def test_ensure_indexes_covers_leaderboard_and_claimable() -> None:
    source = inspect.getsource(ensure_indexes)
    assert "donation_given" in source
    assert "count_worker_rating" in source
    assert "item_sold" in source
    assert "order_claims.order_claimable" in source
    assert "status" in source and "ends_at" in source
    assert "world_id" in source
