"""Global secrets from .env (channel/role IDs live in each game config)."""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE, override=True)

log = logging.getLogger("core.settings")

_settings: Settings | None = None


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"ENV variable not found: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    DISCORD_TOKEN: str
    MONGO_URI: str


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings(
            DISCORD_TOKEN=_require("DISCORD_TOKEN"),
            MONGO_URI=_require("MONGO_URI"),
        )
    return _settings


class _LazySettings:
    def __getattr__(self, name: str) -> str:
        return getattr(get_settings(), name)


settings = _LazySettings()
