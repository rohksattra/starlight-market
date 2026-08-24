"""Mongo client and database access."""
from __future__ import annotations

import logging

import motor.motor_asyncio

from core.settings import settings

log = logging.getLogger("database.connection")

_client: motor.motor_asyncio.AsyncIOMotorClient | None = None


def _get_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_URI)
        log.info("Mongo client created")
    return _client


def get_db(db_name: str) -> motor.motor_asyncio.AsyncIOMotorDatabase:
    return _get_client()[db_name]


async def ping(*, log_ok: bool = True) -> None:
    await _get_client().admin.command("ping")
    if log_ok:
        log.info("Mongo cluster ping OK")


def get_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    return _get_client()


async def close_mongo() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
        log.info("Mongo client closed")
