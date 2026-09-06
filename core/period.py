"""Time windows for market statistics and leaderboards."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from core.time import utc_now

StatPeriod = Literal["7d", "30d", "all"]

PERIODS: tuple[StatPeriod, ...] = ("7d", "30d", "all")

PERIOD_LABELS: dict[StatPeriod, str] = {
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    "all": "All time",
}

PERIOD_BUTTON_LABELS: dict[StatPeriod, str] = {
    "7d": "7D",
    "30d": "30D",
    "all": "All time",
}


def is_stat_period(value: str) -> bool:
    return value in PERIODS


def period_label(period: StatPeriod) -> str:
    return PERIOD_LABELS[period]


def period_cutoff(period: StatPeriod) -> datetime | None:
    if period == "7d":
        return utc_now() - timedelta(days=7)
    if period == "30d":
        return utc_now() - timedelta(days=30)
    return None


def parse_period_from_custom_id(custom_id: str) -> StatPeriod | None:
    parts = custom_id.split(":")
    if len(parts) >= 2 and parts[-2] == "p" and parts[-1] in PERIODS:
        return parts[-1]  # type: ignore[return-value]
    return None


def parse_period_from_text(text: str) -> StatPeriod:
    if "Last 7 days" in text:
        return "7d"
    if "Last 30 days" in text:
        return "30d"
    return "all"
