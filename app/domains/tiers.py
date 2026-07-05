from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.config import settings


# ================= LIMIT MODELS =================


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


# ================= DONOR TIERS (threshold-aligned) =================

DONOR_TIER_THRESHOLDS: tuple[tuple[int, int], ...] = (
    (1_000_000_000, settings.ASTRALIS_DONOR_ROLE_ID),
    (500_000_000, settings.ELYSIUM_DONOR_ROLE_ID),
    (250_000_000, settings.ZENITH_DONOR_ROLE_ID),
    (100_000_000, settings.AETHER_DONOR_ROLE_ID),
    (50_000_000, settings.SANCTUM_DONOR_ROLE_ID),
    (20_000_000, settings.ORACLE_DONOR_ROLE_ID),
    (5_000_000, settings.RELIC_DONOR_ROLE_ID),
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

# ================= WORKER TIERS =================

WORKER_TIER_THRESHOLDS: tuple[tuple[int, int], ...] = (
    (100_000_000_000, settings.GENESIS_WORKER_ROLE_ID),
    (25_000_000_000, settings.INFINITY_WORKER_ROLE_ID),
    (5_000_000_000, settings.ECLIPSE_WORKER_ROLE_ID),
    (1_000_000_000, settings.NOVA_WORKER_ROLE_ID),
    (250_000_000, settings.ASTRAL_WORKER_ROLE_ID),
    (50_000_000, settings.RANGER_WORKER_ROLE_ID),
    (10_000_000, settings.EXPLORER_WORKER_ROLE_ID),
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

# ================= CUSTOMER TIERS =================

CUSTOMER_TIER_THRESHOLDS: tuple[tuple[int, int], ...] = (
    (100_000_000_000, settings.CELESTIAL_CUSTOMER_ROLE_ID),
    (25_000_000_000, settings.COSMIC_CUSTOMER_ROLE_ID),
    (5_000_000_000, settings.GALACTIC_CUSTOMER_ROLE_ID),
    (1_000_000_000, settings.NEBULA_CUSTOMER_ROLE_ID),
    (250_000_000, settings.STELLAR_CUSTOMER_ROLE_ID),
    (50_000_000, settings.VOYAGER_CUSTOMER_ROLE_ID),
    (10_000_000, settings.WANDERER_CUSTOMER_ROLE_ID),
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

# ================= ROLE ID SETS =================

DONOR_ROLE_IDS: frozenset[int] = frozenset(t[1] for t in DONOR_TIER_THRESHOLDS)
WORKER_TIER_ROLE_IDS: frozenset[int] = frozenset(t[1] for t in WORKER_TIER_THRESHOLDS)
CUSTOMER_TIER_ROLE_IDS: frozenset[int] = frozenset(t[1] for t in CUSTOMER_TIER_THRESHOLDS)
ALL_TIER_ROLE_IDS: frozenset[int] = DONOR_ROLE_IDS | WORKER_TIER_ROLE_IDS | CUSTOMER_TIER_ROLE_IDS


# ================= ROLE RESOLVERS =================


def donor_role_for_total(donation_total: int) -> int | None:
    for threshold, role_id in DONOR_TIER_THRESHOLDS:
        if donation_total >= threshold:
            return role_id
    return None


def worker_tier_role_for_income(income: int) -> int | None:
    for threshold, role_id in WORKER_TIER_THRESHOLDS:
        if income >= threshold:
            return role_id
    return None


def customer_tier_role_for_spent(spent: int) -> int | None:
    for threshold, role_id in CUSTOMER_TIER_THRESHOLDS:
        if spent >= threshold:
            return role_id
    return None


# ================= LIMIT RESOLVERS =================


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
