"""Optional HTTP health endpoint for hosted deployments."""
from __future__ import annotations

import asyncio
import logging
import os
import time

from discord.ext import commands

from database.connection import ping

log = logging.getLogger("core.web")

_bot: commands.Bot | None = None
_HEALTHY_BODY = b"starlight-v2:ok"
_HEALTH_OK_TTL = 5.0
_HEALTH_FAIL_TTL = 2.0
_health_cache: tuple[float, int, bytes] | None = None


def bind_bot(bot: commands.Bot) -> None:
    global _bot
    _bot = bot


def _cached_health(now: float) -> tuple[int, bytes] | None:
    if _health_cache is None:
        return None
    cached_at, status, body = _health_cache
    ttl = _HEALTH_OK_TTL if status == 200 else _HEALTH_FAIL_TTL
    if now - cached_at >= ttl:
        return None
    return status, body


async def _health() -> tuple[int, bytes]:
    global _health_cache
    bot = _bot
    if bot is None or not bot.is_ready():
        return 503, b"discord:not-ready"

    now = time.monotonic()
    cached = _cached_health(now)
    if cached is not None:
        return cached

    try:
        await ping(log_ok=False)
    except Exception:
        log.warning("Health check failed: Mongo unreachable")
        result = (503, b"mongo:unreachable")
        _health_cache = (now, *result)
        return result
    result = (200, _HEALTHY_BODY)
    _health_cache = (now, *result)
    return result


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        data = await asyncio.wait_for(reader.read(2048), timeout=5)
    except Exception:
        writer.close()
        await writer.wait_closed()
        return

    request = data.decode("latin-1", errors="replace")
    first = request.split("\r\n", 1)[0]
    method = first.split(" ")[0].upper() if first else "GET"
    status, body = await _health()
    reason = "OK" if status == 200 else "Service Unavailable"
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    writer.write(headers if method == "HEAD" else headers + body)
    try:
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def start_health_server(bot: commands.Bot | None = None) -> asyncio.AbstractServer:
    if bot is not None:
        bind_bot(bot)
    port = int(os.getenv("PORT", "10000"))
    server = await asyncio.start_server(_handle_client, "0.0.0.0", port)
    log.info("Health server listening on 0.0.0.0:%s", port)
    return server
