"""
Stores only global secrets.
Channel/role/category IDs live in games/<game>/config.yaml — not here.
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Always prefer starlight_v2/.env over a leftover shell MONGO_URI (e.g. localhost).
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE, override=True)

log = logging.getLogger("core.settings")


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"ENV variable not found: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    DISCORD_TOKEN: str = _require("DISCORD_TOKEN")
    MONGO_URI: str = _require("MONGO_URI")


settings = Settings()
