from __future__ import annotations

from core.time import coupon_month_key, coupons_used_for_month
from services.tiers import (
    DONOR_LIMITS_BY_TIER,
    donor_has_coupons,
    donor_limits_for_total,
    donor_tier_for_total,
    format_limit_remaining,
    worker_tier_for_income,
    customer_tier_for_spent,
)


def test_donor_coupon_counts_by_tier() -> None:
    assert DONOR_LIMITS_BY_TIER["relic"].max_coupons == 1
    assert DONOR_LIMITS_BY_TIER["oracle"].max_coupons == 3
    assert DONOR_LIMITS_BY_TIER["sanctum"].max_coupons == 5
    assert DONOR_LIMITS_BY_TIER["aether"].max_coupons == 7
    assert DONOR_LIMITS_BY_TIER["zenith"].max_coupons == 9
    assert DONOR_LIMITS_BY_TIER["elysium"].max_coupons == 12
    assert DONOR_LIMITS_BY_TIER["astralis"].max_coupons is None


def test_coa_donor_thresholds() -> None:
    assert donor_tier_for_total(4_999_999, game="coa") is None
    assert donor_tier_for_total(5_000_000, game="coa") == "relic"
    assert donor_tier_for_total(1_000_000_000, game="coa") == "astralis"
    assert donor_limits_for_total(5_000_000, game="coa").max_coupons == 1
    assert donor_limits_for_total(1_000_000_000, game="coa").max_coupons is None


def test_eop_thresholds_are_one_digit_smaller() -> None:
    assert donor_tier_for_total(500_000, game="eop") == "relic"
    assert donor_tier_for_total(5_000_000, game="eop") == "sanctum"
    assert donor_tier_for_total(100_000_000, game="eop") == "astralis"
    assert worker_tier_for_income(1_000_000, game="eop") == "explorer"
    assert worker_tier_for_income(10_000_000, game="coa") == "explorer"
    assert worker_tier_for_income(1_000_000, game="coa") is None
    assert customer_tier_for_spent(1_000_000, game="eop") == "wanderer"
    assert customer_tier_for_spent(10_000_000, game="coa") == "wanderer"


def test_same_gold_unlocks_higher_eop_tier() -> None:
    assert donor_tier_for_total(10_000_000, game="coa") == "relic"
    assert donor_tier_for_total(10_000_000, game="eop") == "aether"
    assert worker_tier_for_income(100_000_000, game="coa") == "ranger"
    assert worker_tier_for_income(100_000_000, game="eop") == "nova"


def test_unlimited_coupons_are_available() -> None:
    limits = donor_limits_for_total(1_000_000_000, game="coa")
    assert donor_has_coupons(limits)
    assert format_limit_remaining(remaining=0, maximum=limits.max_coupons) == "Unlimited"


def test_no_donor_has_no_coupons() -> None:
    limits = donor_limits_for_total(0, game="coa")
    assert limits.max_coupons == 0
    assert not donor_has_coupons(limits)


def test_coupon_usage_resets_on_new_month() -> None:
    assert coupons_used_for_month(stored_month=202607, stored_count=5, month_key=202608) == 0
    assert coupons_used_for_month(stored_month=202608, stored_count=5, month_key=202608) == 5


def test_coupon_month_key_format() -> None:
    key = coupon_month_key()
    assert 202001 <= key <= 210012
    assert 1 <= key % 100 <= 12
