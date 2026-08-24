"""UTC clock. Drop-in for deprecated datetime.utcnow()."""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Naive UTC now — matches Motor's decoded BSON dates."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def coupon_month_key(when: datetime | None = None) -> int:
    """YYYYMM key used to reset monthly donor coupons on the 1st (UTC)."""
    moment = when or utc_now()
    return moment.year * 100 + moment.month


def coupons_used_for_month(*, stored_month: int, stored_count: int, month_key: int) -> int:
    if stored_month != month_key:
        return 0
    return max(0, stored_count)
