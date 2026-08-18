"""Optional HTTP health endpoint for hosted deployments."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from discord.ext import commands

from database.connection import ping

log = logging.getLogger("core.web")

_bot: commands.Bot | None = None
_HEALTHY_BODY = b"starlight-v2:ok"


def bind_bot(bot: commands.Bot) -> None:
    global _bot
    _bot = bot


def _health() -> tuple[int, bytes]:
    bot = _bot
    if bot is None or not bot.is_ready():
        return 503, b"discord:not-ready"
    loop = getattr(bot, "loop", None)
    if loop is None or not loop.is_running():
        return 503, b"discord:not-ready"
    try:
        asyncio.run_coroutine_threadsafe(ping(log_ok=False), loop).result(timeout=3)
    except Exception:
        log.warning("Health check failed: Mongo unreachable")
        return 503, b"mongo:unreachable"
    return 200, _HEALTHY_BODY


class HealthHandler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        status, _ = _health()
        self.send_response(status)
        self.end_headers()

    def do_GET(self) -> None:
        status, body = _health()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def start_web_background(bot: commands.Bot | None = None) -> None:
    if bot is not None:
        bind_bot(bot)
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
