from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from core.period import (
    parse_period_from_custom_id,
    parse_period_from_text,
    period_cutoff,
    period_label,
)


def test_period_labels() -> None:
    assert period_label("7d") == "Last 7 days"
    assert period_label("30d") == "Last 30 days"
    assert period_label("all") == "All time"


def test_parse_period_from_text() -> None:
    assert parse_period_from_text("**Period:** Last 7 days") == "7d"
    assert parse_period_from_text("🏆 Top 100 Workers · Last 30 days") == "30d"
    assert parse_period_from_text("📊 Market Statistics") == "all"
    assert parse_period_from_text("") == "all"


def test_parse_period_from_custom_id() -> None:
    assert parse_period_from_custom_id("market_stat:p:7d") == "7d"
    assert parse_period_from_custom_id("leaderboard:worker:p:30d") == "30d"
    assert parse_period_from_custom_id("leaderboard:rated:p:all") == "all"
    assert parse_period_from_custom_id("market_stat:refresh") is None
    assert parse_period_from_custom_id("leaderboard:worker:next") is None


def test_period_cutoff_all_is_none() -> None:
    assert period_cutoff("all") is None


def test_period_cutoff_windows() -> None:
    now = datetime(2026, 8, 17, 12, 0, 0)
    with patch("core.period.utc_now", return_value=now):
        assert period_cutoff("7d") == datetime(2026, 8, 10, 12, 0, 0)
        assert period_cutoff("30d") == datetime(2026, 7, 18, 12, 0, 0)
