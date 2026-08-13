"""Tier thresholds and limits (role IDs live in each game config)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DonorLimits:
    max_coupons: int


@dataclass(frozen=True)
class WorkerLimits:
    max_claim_orders: int
    claim_capacity: int | None


@dataclass(frozen=True)
class CustomerLimits:
    max_active_orders: int
    order_capacity: int | None


DEFAULT_WORKER_LIMITS = WorkerLimits(max_claim_orders=3, claim_capacity=5_000)
DEFAULT_CUSTOMER_LIMITS = CustomerLimits(max_active_orders=3, order_capacity=5_000)
NO_DONOR_LIMITS = DonorLimits(max_coupons=0)


DONOR_TIER_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (1_000_000_000, "astralis"),
    (500_000_000, "elysium"),
    (250_000_000, "zenith"),
    (100_000_000, "aether"),
    (50_000_000, "sanctum"),
    (20_000_000, "oracle"),
    (5_000_000, "relic"),
)

DONOR_TIER_LIMITS: tuple[tuple[int, DonorLimits], ...] = (
    (1_000_000_000, DonorLimits(max_coupons=12)),
    (500_000_000, DonorLimits(max_coupons=10)),
    (250_000_000, DonorLimits(max_coupons=8)),
    (100_000_000, DonorLimits(max_coupons=6)),
    (50_000_000, DonorLimits(max_coupons=4)),
    (20_000_000, DonorLimits(max_coupons=2)),
    (5_000_000, DonorLimits(max_coupons=1)),
)

WORKER_TIER_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (100_000_000_000, "genesis"),
    (25_000_000_000, "infinity"),
    (5_000_000_000, "eclipse"),
    (1_000_000_000, "nova"),
    (250_000_000, "astral"),
    (50_000_000, "ranger"),
    (10_000_000, "explorer"),
)

WORKER_TIER_LIMITS: tuple[tuple[int, WorkerLimits], ...] = (
    (100_000_000_000, WorkerLimits(max_claim_orders=6, claim_capacity=None)),
    (25_000_000_000, WorkerLimits(max_claim_orders=6, claim_capacity=100_000)),
    (5_000_000_000, WorkerLimits(max_claim_orders=5, claim_capacity=75_000)),
    (1_000_000_000, WorkerLimits(max_claim_orders=5, claim_capacity=50_000)),
    (250_000_000, WorkerLimits(max_claim_orders=4, claim_capacity=35_000)),
    (50_000_000, WorkerLimits(max_claim_orders=4, claim_capacity=20_000)),
    (10_000_000, WorkerLimits(max_claim_orders=3, claim_capacity=10_000)),
)

CUSTOMER_TIER_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (100_000_000_000, "celestial"),
    (25_000_000_000, "cosmic"),
    (5_000_000_000, "galactic"),
    (1_000_000_000, "nebula"),
    (250_000_000, "stellar"),
    (50_000_000, "voyager"),
    (10_000_000, "wanderer"),
)

CUSTOMER_TIER_LIMITS: tuple[tuple[int, CustomerLimits], ...] = (
    (100_000_000_000, CustomerLimits(max_active_orders=12, order_capacity=None)),
    (25_000_000_000, CustomerLimits(max_active_orders=10, order_capacity=500_000)),
    (5_000_000_000, CustomerLimits(max_active_orders=8, order_capacity=250_000)),
    (1_000_000_000, CustomerLimits(max_active_orders=7, order_capacity=100_000)),
    (250_000_000, CustomerLimits(max_active_orders=6, order_capacity=50_000)),
    (50_000_000, CustomerLimits(max_active_orders=5, order_capacity=20_000)),
    (10_000_000, CustomerLimits(max_active_orders=4, order_capacity=10_000)),
)


def donor_tier_for_total(donation_total: int) -> str | None:
    for threshold, tier in DONOR_TIER_THRESHOLDS:
        if donation_total >= threshold:
            return tier
    return None


def worker_tier_for_income(income: int) -> str | None:
    for threshold, tier in WORKER_TIER_THRESHOLDS:
        if income >= threshold:
            return tier
    return None


def customer_tier_for_spent(spent: int) -> str | None:
    for threshold, tier in CUSTOMER_TIER_THRESHOLDS:
        if spent >= threshold:
            return tier
    return None


def donor_limits_for_total(donation_total: int) -> DonorLimits:
    for threshold, limits in DONOR_TIER_LIMITS:
        if donation_total >= threshold:
            return limits
    return NO_DONOR_LIMITS


def worker_limits_for_income(income: int) -> WorkerLimits:
    for threshold, limits in WORKER_TIER_LIMITS:
        if income >= threshold:
            return limits
    return DEFAULT_WORKER_LIMITS


def customer_limits_for_spent(spent: int) -> CustomerLimits:
    for threshold, limits in CUSTOMER_TIER_LIMITS:
        if spent >= threshold:
            return limits
    return DEFAULT_CUSTOMER_LIMITS


def format_limit_remaining(*, remaining: int, maximum: int | None) -> str:
    if maximum is None:
        return "Unlimited"
    return f"{remaining:,}/{maximum:,}"


def current_coupon_month_key() -> int:
    now = datetime.utcnow()
    return now.year * 100 + now.month
