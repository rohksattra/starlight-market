from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import core.web as web


def _run(coro):
    return asyncio.run(coro)


def setup_function() -> None:
    web._bot = None
    web._health_cache = None


def test_health_not_ready_without_bot() -> None:
    status, body = _run(web._health())
    assert status == 503
    assert body == b"discord:not-ready"


def test_health_caches_successful_mongo_ping() -> None:
    bot = MagicMock()
    bot.is_ready.return_value = True
    web.bind_bot(bot)
    with (
        patch("core.web.time.monotonic", return_value=100.0),
        patch("core.web.ping", new=AsyncMock()) as ping,
    ):
        first = _run(web._health())
        second = _run(web._health())
    assert first == (200, web._HEALTHY_BODY)
    assert second == first
    assert ping.await_count == 1
