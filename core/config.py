# core/config.py
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv


log = logging.getLogger("core.config")

load_dotenv()
log.info(".env file loaded")

WORKER_FEE_RATE: float = 0.99


def _require(value: str | None, name: str) -> str:
    if not value:
        log.error("ENV missing: %s", name)
        raise RuntimeError(f"{name} is not set")
    return value


def _require_int(value: str | None, name: str) -> int:
    if not value:
        log.error("ENV missing: %s", name)
        raise RuntimeError(f"{name} is not set")
    try:
        return int(value)
    except ValueError:
        log.error("ENV invalid integer: %s", name)
        raise RuntimeError(f"{name} must be an integer")


@dataclass(frozen=True)
class Settings:
    # ================= DATABASE =================
    MONGO_DB_URI: str = _require(os.getenv("MONGO_DB_URI"), "MONGO_DB_URI")
    MONGO_DB_NAME: str = _require(os.getenv("MONGO_DB_NAME"), "MONGO_DB_NAME")
    # ================= DISCORD =================
    DISCORD_TOKEN: str = _require(os.getenv("DISCORD_TOKEN"), "DISCORD_TOKEN")
    GUILD_ID: int = _require_int(os.getenv("GUILD_ID"), "GUILD_ID")
    # ================= ROLE IDS =================
    BOT_DEVELOPER_ROLE_ID: int = _require_int(os.getenv("BOT_DEVELOPER_ROLE_ID"), "BOT_DEVELOPER_ROLE_ID")
    BANK_MANAGER_ROLE_ID: int = _require_int(os.getenv("BANK_MANAGER_ROLE_ID"), "BANK_MANAGER_ROLE_ID")
    MODERATOR_ROLE_ID: int = _require_int(os.getenv("MODERATOR_ROLE_ID"), "MODERATOR_ROLE_ID")
    WORKER_ROLE_ID: int = _require_int(os.getenv("WORKER_ROLE_ID"), "WORKER_ROLE_ID")
    CUSTOMER_ROLE_ID: int = _require_int(os.getenv("CUSTOMER_ROLE_ID"), "CUSTOMER_ROLE_ID")
    # ================= CATEGORY IDS =================
    NEW_ORDERS_CATEGORY_ID: int = _require_int(os.getenv("NEW_ORDERS_CATEGORY_ID"), "NEW_ORDERS_CATEGORY_ID")
    CLAIMED_ORDERS_CATEGORY_ID: int = _require_int(os.getenv("CLAIMED_ORDERS_CATEGORY_ID"), "CLAIMED_ORDERS_CATEGORY_ID")
    COMPLETED_ORDERS_CATEGORY_ID: int = _require_int(os.getenv("COMPLETED_ORDERS_CATEGORY_ID"), "COMPLETED_ORDERS_CATEGORY_ID")
    # ================= CHANNEL IDS =================
    WELCOME_CHANNEL_ID: int = _require_int(os.getenv("WELCOME_CHANNEL_ID"), "WELCOME_CHANNEL_ID")
    FAREWELL_CHANNEL_ID: int = _require_int(os.getenv("FAREWELL_CHANNEL_ID"), "FAREWELL_CHANNEL_ID")
    PLACE_ORDER_CHANNEL_ID: int = _require_int(os.getenv("PLACE_ORDER_CHANNEL_ID"), "PLACE_ORDER_CHANNEL_ID")
    CLAIM_MESSAGE_CHANNEL_ID: int = _require_int(os.getenv("CLAIM_MESSAGE_CHANNEL_ID"), "CLAIM_MESSAGE_CHANNEL_ID")
    RATING_MESSAGE_CHANNEL_ID: int = _require_int(os.getenv("RATING_MESSAGE_CHANNEL_ID"), "RATING_MESSAGE_CHANNEL_ID")
    TRANSACTION_CHANNEL_ID: int = _require_int(os.getenv("TRANSACTION_CHANNEL_ID"), "TRANSACTION_CHANNEL_ID")
    TOP_WORKER_CHANNEL_ID: int = _require_int(os.getenv("TOP_WORKER_CHANNEL_ID"), "TOP_WORKER_CHANNEL_ID")
    TOP_CUSTOMER_CHANNEL_ID: int = _require_int(os.getenv("TOP_CUSTOMER_CHANNEL_ID"), "TOP_CUSTOMER_CHANNEL_ID")
    TOP_ITEM_CHANNEL_ID: int = _require_int(os.getenv("TOP_ITEM_CHANNEL_ID"), "TOP_ITEM_CHANNEL_ID")
    COUNTING_CHANNEL_ID: int = _require_int(os.getenv("COUNTING_CHANNEL_ID"), "COUNTING_CHANNEL_ID")


settings = Settings()
log.info("Environment configuration validated")
