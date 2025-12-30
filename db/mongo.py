# db/mongo.py
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from core.config import settings


_client: AsyncIOMotorClient | None = None
_db = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_DB_URI, uuidRepresentation="standard")
    return _client


def get_db():
    global _db
    if _db is None:
        _db = get_client()[settings.MONGO_DB_NAME]
    return _db


async def ping() -> None:
    try:
        await get_client().admin.command("ping")
    except ConnectionFailure as exc:
        raise RuntimeError("MongoDB connection failed") from exc


async def close_mongo() -> None:
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
