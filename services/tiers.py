"""Per-game tier thresholds and limits (role IDs live in each game config)."""
from __future__ import annotations

from dataclasses import dataclass

from core.time import coupon_month_key


@dataclass(frozen=True)
class DonorLimits:
    max_coupons: int | None


@dataclass(frozen=True)
class WorkerLimits:
    max_claim_orders: int
    claim_capacity: int | None


@dataclass(frozen=True)
class CustomerLimits:
    max_active_orders: int
    order_capacity: int | None


@dataclass(frozen=True)
class GameEconomyTiers:
    donor_thresholds: tuple[tuple[int, str], ...]
    worker_thresholds: tuple[tuple[int, str], ...]
    customer_thresholds: tuple[tuple[int, str], ...]


DEFAULT_WORKER_LIMITS = WorkerLimits(max_claim_orders=3, claim_capacity=5_000)
DEFAULT_CUSTOMER_LIMITS = CustomerLimits(max_active_orders=3, order_capacity=5_000)
NO_DONOR_LIMITS = DonorLimits(max_coupons=0)

DONOR_LIMITS_BY_TIER: dict[str, DonorLimits] = {
    "relic": DonorLimits(max_coupons=1),
    "oracle": DonorLimits(max_coupons=3),
    "sanctum": DonorLimits(max_coupons=5),
    "aether": DonorLimits(max_coupons=7),
    "zenith": DonorLimits(max_coupons=9),
    "elysium": DonorLimits(max_coupons=12),
    "astralis": DonorLimits(max_coupons=None),
}

WORKER_LIMITS_BY_TIER: dict[str, WorkerLimits] = {
    "explorer": WorkerLimits(max_claim_orders=3, claim_capacity=10_000),
    "ranger": WorkerLimits(max_claim_orders=4, claim_capacity=20_000),
    "astral": WorkerLimits(max_claim_orders=4, claim_capacity=35_000),
    "nova": WorkerLimits(max_claim_orders=5, claim_capacity=50_000),
    "eclipse": WorkerLimits(max_claim_orders=5, claim_capacity=75_000),
    "infinity": WorkerLimits(max_claim_orders=6, claim_capacity=100_000),
    "genesis": WorkerLimits(max_claim_orders=6, claim_capacity=None),
}

CUSTOMER_LIMITS_BY_TIER: dict[str, CustomerLimits] = {
    "wanderer": CustomerLimits(max_active_orders=4, order_capacity=10_000),
    "voyager": CustomerLimits(max_active_orders=5, order_capacity=20_000),
    "stellar": CustomerLimits(max_active_orders=6, order_capacity=50_000),
    "nebula": CustomerLimits(max_active_orders=7, order_capacity=100_000),
    "galactic": CustomerLimits(max_active_orders=8, order_capacity=250_000),
    "cosmic": CustomerLimits(max_active_orders=10, order_capacity=500_000),
    "celestial": CustomerLimits(max_active_orders=12, order_capacity=None),
}

COA_TIERS = GameEconomyTiers(
    donor_thresholds=(
        (1_000_000_000, "astralis"),
        (500_000_000, "elysium"),
        (250_000_000, "zenith"),
        (100_000_000, "aether"),
        (50_000_000, "sanctum"),
        (20_000_000, "oracle"),
        (5_000_000, "relic"),
    ),
    worker_thresholds=(
        (100_000_000_000, "genesis"),
        (25_000_000_000, "infinity"),
        (5_000_000_000, "eclipse"),
        (1_000_000_000, "nova"),
        (250_000_000, "astral"),
        (50_000_000, "ranger"),
        (10_000_000, "explorer"),
    ),
    customer_thresholds=(
        (100_000_000_000, "celestial"),
        (25_000_000_000, "cosmic"),
        (5_000_000_000, "galactic"),
        (1_000_000_000, "nebula"),
        (250_000_000, "stellar"),
        (50_000_000, "voyager"),
        (10_000_000, "wanderer"),
    ),
)

EOP_TIERS = GameEconomyTiers(
    donor_thresholds=(
        (100_000_000, "astralis"),
        (50_000_000, "elysium"),
        (25_000_000, "zenith"),
        (10_000_000, "aether"),
        (5_000_000, "sanctum"),
        (2_000_000, "oracle"),
        (500_000, "relic"),
    ),
    worker_thresholds=(
        (10_000_000_000, "genesis"),
        (2_500_000_000, "infinity"),
        (500_000_000, "eclipse"),
        (100_000_000, "nova"),
        (25_000_000, "astral"),
        (5_000_000, "ranger"),
        (1_000_000, "explorer"),
    ),
    customer_thresholds=(
        (10_000_000_000, "celestial"),
        (2_500_000_000, "cosmic"),
        (500_000_000, "galactic"),
        (100_000_000, "nebula"),
        (25_000_000, "stellar"),
        (5_000_000, "voyager"),
        (1_000_000, "wanderer"),
    ),
)

GAME_TIERS: dict[str, GameEconomyTiers] = {
    "coa": COA_TIERS,
    "eop": EOP_TIERS,
}


def _tables(game: str) -> GameEconomyTiers:
    return GAME_TIERS.get(game, COA_TIERS)


def _tier_name(amount: int, thresholds: tuple[tuple[int, str], ...]) -> str | None:
    for threshold, tier in thresholds:
        if amount >= threshold:
            return tier
    return None


def donor_tier_for_total(donation_total: int, *, game: str) -> str | None:
    return _tier_name(donation_total, _tables(game).donor_thresholds)


def worker_tier_for_income(income: int, *, game: str) -> str | None:
    return _tier_name(income, _tables(game).worker_thresholds)


def customer_tier_for_spent(spent: int, *, game: str) -> str | None:
    return _tier_name(spent, _tables(game).customer_thresholds)


def donor_limits_for_total(donation_total: int, *, game: str) -> DonorLimits:
    name = donor_tier_for_total(donation_total, game=game)
    if name is None:
        return NO_DONOR_LIMITS
    return DONOR_LIMITS_BY_TIER[name]


def worker_limits_for_income(income: int, *, game: str) -> WorkerLimits:
    name = worker_tier_for_income(income, game=game)
    if name is None:
        return DEFAULT_WORKER_LIMITS
    return WORKER_LIMITS_BY_TIER[name]


def customer_limits_for_spent(spent: int, *, game: str) -> CustomerLimits:
    name = customer_tier_for_spent(spent, game=game)
    if name is None:
        return DEFAULT_CUSTOMER_LIMITS
    return CUSTOMER_LIMITS_BY_TIER[name]


def donor_has_coupons(limits: DonorLimits) -> bool:
    return limits.max_coupons is None or limits.max_coupons > 0


def format_limit_remaining(*, remaining: int, maximum: int | None) -> str:
    if maximum is None:
        return "Unlimited"
    return f"{remaining:,}/{maximum:,}"


def current_coupon_month_key() -> int:
    return coupon_month_key()
