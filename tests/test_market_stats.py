from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.market import MarketService


def _service(*, fee_rate: float = 0.01) -> MarketService:
    ctx = MagicMock()
    ctx.db_name = "test"
    ctx.economy.worker_fee_rate = fee_rate
    with (
        patch("services.market.OrderRepo"),
        patch("services.market.StatisticRepo"),
        patch("services.market.LeaderboardRepo"),
        patch("services.market.ItemRepo"),
        patch("services.market.TransactionRepo"),
        patch("services.market.DonationRepo"),
        patch("services.market.WorkerRatingRepo"),
    ):
        return MarketService(ctx)


def test_avg_order_size() -> None:
    assert MarketService._avg_order_size(items_sold=10, created=4) == 3
    assert MarketService._avg_order_size(items_sold=10, created=3) == 3
    assert MarketService._avg_order_size(items_sold=10, created=0) == 0


def test_commission_uses_tenant_fee() -> None:
    service = _service(fee_rate=0.01)
    assert service._commission(1000) == 10
    service = _service(fee_rate=0.05)
    assert service._commission(1000) == 50
