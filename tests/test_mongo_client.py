from __future__ import annotations

from unittest.mock import MagicMock, patch

import database.connection as connection
from database.connection import MONGO_CLIENT_OPTIONS


def setup_function() -> None:
    connection._client = None


def teardown_function() -> None:
    connection._client = None


def test_mongo_client_sets_timeouts_and_pool() -> None:
    settings = MagicMock()
    settings.MONGO_URI = "mongodb://localhost:27017"
    with (
        patch.object(connection, "settings", settings),
        patch("database.connection.motor.motor_asyncio.AsyncIOMotorClient") as client_cls,
    ):
        connection._get_client()
    assert client_cls.call_args.args[0] == "mongodb://localhost:27017"
    kwargs = client_cls.call_args.kwargs
    assert kwargs["serverSelectionTimeoutMS"] == MONGO_CLIENT_OPTIONS["serverSelectionTimeoutMS"]
    assert kwargs["connectTimeoutMS"] == 5_000
    assert kwargs["socketTimeoutMS"] == 20_000
    assert kwargs["maxPoolSize"] == 50
