"""Mongo helpers for claim/income integration tests.

Skipped locally when Mongo is down. CI must provide a replica set so
transaction tests run instead of skip.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import fields, MISSING
from typing import Any, Awaitable, Callable
from uuid import uuid4

import pytest

from core.tenant import (
    AssetsConfig,
    BrandConfig,
    ChannelConfig,
    EconomyConfig,
    GameContext,
    RoleConfig,
)
from models.enums import OrderStatus
from models.order import OrderCreate

_TEST_DB_PREFIX = "sit_"
_mongo_status: tuple[str, str] | None = None

MongoTest = Callable[[GameContext], Awaitable[None]]


def _dummy_dataclass(cls, **overrides):
    kwargs = dict(overrides)
    for field in fields(cls):
        if field.name in kwargs:
            continue
        if field.default is not MISSING or field.default_factory is not MISSING:
            continue
        origin = getattr(field.type, "__origin__", field.type)
        if origin is dict:
            kwargs[field.name] = {}
        elif field.type is float or origin is float:
            kwargs[field.name] = 0.0
        elif field.type is str or origin is str:
            kwargs[field.name] = ""
        else:
            kwargs[field.name] = 0
    return cls(**kwargs)


def make_test_context(db_name: str, *, game: str = "coa") -> GameContext:
    return GameContext(
        game=game,
        guild_id=1,
        db_name=db_name,
        channels=_dummy_dataclass(ChannelConfig),
        roles=_dummy_dataclass(RoleConfig),
        economy=_dummy_dataclass(EconomyConfig, worker_fee_rate=0.01),
        assets=AssetsConfig(),
        brand=BrandConfig(),
    )


def sample_order(
    *,
    order_id: str = "ord-1",
    channel_id: str = "ch-1",
    customer_id: str = "c1",
    item_id: str = "item-1",
    item_quantity: int = 10,
    item_price: int = 100,
    coupon_applied: bool = False,
    **overrides: Any,
) -> OrderCreate:
    doc: dict[str, Any] = {
        "order_id": order_id,
        "order_number": 1,
        "channel_id": channel_id,
        "embed_message_id": "",
        "customer_id": customer_id,
        "item_id": item_id,
        "item_name": "Iron Ore",
        "item_price": item_price,
        "item_quantity": item_quantity,
        "item_image": "",
        "item_category": "ore",
        "is_custom": False,
        "worker_claims": {},
        "order_claims": {
            "order_delivered": 0,
            "order_completed": 0,
            "order_claimed": 0,
            "order_claimable": item_quantity,
        },
        "order_status": OrderStatus.NEW,
        "coupon_applied": coupon_applied,
    }
    doc.update(overrides)
    return doc  # type: ignore[return-value]


def _skip_or_fail(reason: str) -> None:
    if os.environ.get("CI"):
        raise RuntimeError(reason)
    pytest.skip(reason)


def mongo_status() -> tuple[str, str]:
    global _mongo_status
    if _mongo_status is not None:
        return _mongo_status

    try:
        from core.settings import settings

        uri = settings.MONGO_URI
    except RuntimeError as exc:
        _mongo_status = ("down", str(exc))
        return _mongo_status

    import motor.motor_asyncio

    client = motor.motor_asyncio.AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2500)
    hello: dict[str, Any] | None = None
    error: Exception | None = None

    async def _ping() -> dict[str, Any]:
        await client.admin.command("ping")
        return await client.admin.command("hello")

    try:
        hello = asyncio.run(_ping())
    except Exception as exc:
        error = exc
    finally:
        client.close()

    if error is not None:
        _mongo_status = ("down", f"MongoDB unavailable: {error}")
    elif hello and (hello.get("setName") or hello.get("msg") == "isdbgrid"):
        _mongo_status = ("ok", "")
    else:
        _mongo_status = ("standalone", "Mongo replica set required for transactions")
    return _mongo_status


def require_mongo(*, replica: bool = False) -> None:
    kind, reason = mongo_status()
    if kind == "down":
        _skip_or_fail(reason)
    if replica and kind != "ok":
        _skip_or_fail(reason)


def run_mongo_test(fn: MongoTest, *, replica: bool = False) -> None:
    require_mongo(replica=replica)

    from database.connection import close_mongo, get_client

    async def body() -> None:
        db_name = f"{_TEST_DB_PREFIX}{uuid4().hex[:12]}"
        assert db_name.startswith(_TEST_DB_PREFIX)
        try:
            await fn(make_test_context(db_name))
        finally:
            try:
                await get_client().drop_database(db_name)
            finally:
                await close_mongo()

    asyncio.run(body())
