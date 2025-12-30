# db/mongo.py
from __future__ import annotations

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
from core.config import settings


_client: AsyncIOMotorClient | None = None
_db = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            settings.MONGO_DB_URI,
            uuidRepresentation="standard",
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=5000,
        )
    return _client


def get_db():
    global _db
    if _db is None:
        _db = get_client()[settings.MONGO_DB_NAME]
    return _db


async def ping(retry: int = 3) -> None:
    for i in range(retry):
        try:
            await get_client().admin.command("ping")
            return
        except PyMongoError:
            if i == retry - 1:
                raise RuntimeError("MongoDB connection failed")
            await asyncio.sleep(2)


async def close_mongo() -> None:
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
