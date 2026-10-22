"""Market fee rate (commission) resolved from DB, keyed by tenant database name."""
from __future__ import annotations

import asyncio
import logging

from core.tenant import GameContext
from database.settings import SettingRepo

log = logging.getLogger("services.market_settings")

_fee_rates: dict[str, float] = {}
_locks: dict[str, asyncio.Lock] = {}

MIN_FEE_RATE = 0.0
MAX_FEE_RATE = 0.5


def _lock(db_name: str) -> asyncio.Lock:
    lock = _locks.get(db_name)
    if lock is None:
        lock = asyncio.Lock()
        _locks[db_name] = lock
    return lock


def invalidate(db_name: str) -> None:
    _fee_rates.pop(db_name, None)


def clear() -> None:
    _fee_rates.clear()


def cached_fee_rate(db_name: str, *, default: float | None = None) -> float | None:
    rate = _fee_rates.get(db_name)
    if rate is None:
        return default
    return rate


def clamp_fee_rate(fee_rate: float) -> float:
    return max(MIN_FEE_RATE, min(MAX_FEE_RATE, float(fee_rate)))


def parse_fee_rate(value: str) -> float:
    """Parse a staff input into a fee rate (accepts `1`, `1%`, or `0.01`)."""
    text = value.strip().replace("%", "").replace(",", ".")
    if not text:
        raise ValueError("Fee rate is empty")
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError("Fee rate must be a number") from exc

    fee_rate = number / 100 if number > MAX_FEE_RATE else number
    if fee_rate < MIN_FEE_RATE or fee_rate > MAX_FEE_RATE:
        raise ValueError(
            f"Fee rate must be between {MIN_FEE_RATE * 100:g}% and {MAX_FEE_RATE * 100:g}%"
        )
    return fee_rate


def format_fee_rate(fee_rate: float) -> str:
    percent = float(fee_rate) * 100
    if percent == int(percent):
        return f"{int(percent)}%"
    return f"{percent:g}%"


async def get_fee_rate(ctx: GameContext) -> float:
    """Fee rate from DB, seeded from config on first read."""
    cached = _fee_rates.get(ctx.db_name)
    if cached is not None:
        return cached

    async with _lock(ctx.db_name):
        cached = _fee_rates.get(ctx.db_name)
        if cached is not None:
            return cached

        repo = SettingRepo(ctx.db_name)
        doc = await repo.get_market()
        if doc is None:
            default = clamp_fee_rate(ctx.economy.worker_fee_rate)
            await repo.seed_market_fee_rate(fee_rate=default)
            _fee_rates[ctx.db_name] = default
            log.info("Market fee rate seeded | db=%s rate=%s", ctx.db_name, default)
            return default

        rate = clamp_fee_rate(doc.get("market_fee_rate", ctx.economy.worker_fee_rate))
        _fee_rates[ctx.db_name] = rate
        return rate


async def set_fee_rate(ctx: GameContext, *, fee_rate: float, updated_by: str) -> float:
    rate = clamp_fee_rate(fee_rate)
    await SettingRepo(ctx.db_name).set_market_fee_rate(
        fee_rate=rate,
        updated_by=updated_by,
    )
    _fee_rates[ctx.db_name] = rate
    log.info(
        "Market fee rate updated | db=%s rate=%s by=%s",
        ctx.db_name,
        rate,
        updated_by,
    )
    return rate


async def keep_rate(ctx: GameContext) -> float:
    return 1.0 - await get_fee_rate(ctx)
