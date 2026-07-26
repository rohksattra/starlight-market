from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv


log = logging.getLogger("core.config")

load_dotenv()
log.info(".env file loaded")

from core.constants import WORKER_FEE_RATE


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
    # ================= GITHUB (untuk images) =================
    GITHUB_USER: str = _require(os.getenv("GITHUB_USER"), "GITHUB_USER")
    GITHUB_REPO: str = _require(os.getenv("GITHUB_REPO"), "GITHUB_REPO")
    GITHUB_BRANCH: str = _require(os.getenv("GITHUB_BRANCH"), "GITHUB_BRANCH")
    # ================= ROLE IDS =================
    BOT_DEVELOPER_ROLE_ID: int = _require_int(os.getenv("BOT_DEVELOPER_ROLE_ID"), "BOT_DEVELOPER_ROLE_ID")
    BANK_MANAGER_ROLE_ID: int = _require_int(os.getenv("BANK_MANAGER_ROLE_ID"), "BANK_MANAGER_ROLE_ID")
    MODERATOR_ROLE_ID: int = _require_int(os.getenv("MODERATOR_ROLE_ID"), "MODERATOR_ROLE_ID")
    WORKER_ROLE_ID: int = _require_int(os.getenv("WORKER_ROLE_ID"), "WORKER_ROLE_ID")
    CUSTOMER_ROLE_ID: int = _require_int(os.getenv("CUSTOMER_ROLE_ID"), "CUSTOMER_ROLE_ID")
    ANNOUNCEMENT_ROLE_ID: int = _require_int(os.getenv("ANNOUNCEMENT_ROLE_ID"), "ANNOUNCEMENT_ROLE_ID")
    GIVEAWAY_ROLE_ID: int = _require_int(os.getenv("GIVEAWAY_ROLE_ID"), "GIVEAWAY_ROLE_ID")
    CONTENT_NOTIFICATION_ROLE_ID: int = _require_int(os.getenv("CONTENT_NOTIFICATION_ROLE_ID"), "CONTENT_NOTIFICATION_ROLE_ID")
    RELIC_DONOR_ROLE_ID: int = _require_int(os.getenv("RELIC_DONOR_ROLE_ID"), "RELIC_DONOR_ROLE_ID")
    ORACLE_DONOR_ROLE_ID: int = _require_int(os.getenv("ORACLE_DONOR_ROLE_ID"), "ORACLE_DONOR_ROLE_ID")
    SANCTUM_DONOR_ROLE_ID: int = _require_int(os.getenv("SANCTUM_DONOR_ROLE_ID"), "SANCTUM_DONOR_ROLE_ID")
    AETHER_DONOR_ROLE_ID: int = _require_int(os.getenv("AETHER_DONOR_ROLE_ID"), "AETHER_DONOR_ROLE_ID")
    ZENITH_DONOR_ROLE_ID: int = _require_int(os.getenv("ZENITH_DONOR_ROLE_ID"), "ZENITH_DONOR_ROLE_ID")
    ELYSIUM_DONOR_ROLE_ID: int = _require_int(os.getenv("ELYSIUM_DONOR_ROLE_ID"), "ELYSIUM_DONOR_ROLE_ID")
    ASTRALIS_DONOR_ROLE_ID: int = _require_int(os.getenv("ASTRALIS_DONOR_ROLE_ID"), "ASTRALIS_DONOR_ROLE_ID")
    EXPLORER_WORKER_ROLE_ID: int = _require_int(os.getenv("EXPLORER_WORKER_ROLE_ID"), "EXPLORER_WORKER_ROLE_ID")
    RANGER_WORKER_ROLE_ID: int = _require_int(os.getenv("RANGER_WORKER_ROLE_ID"), "RANGER_WORKER_ROLE_ID")
    ASTRAL_WORKER_ROLE_ID: int = _require_int(os.getenv("ASTRAL_WORKER_ROLE_ID"), "ASTRAL_WORKER_ROLE_ID")
    NOVA_WORKER_ROLE_ID: int = _require_int(os.getenv("NOVA_WORKER_ROLE_ID"), "NOVA_WORKER_ROLE_ID")
    ECLIPSE_WORKER_ROLE_ID: int = _require_int(os.getenv("ECLIPSE_WORKER_ROLE_ID"), "ECLIPSE_WORKER_ROLE_ID")
    INFINITY_WORKER_ROLE_ID: int = _require_int(os.getenv("INFINITY_WORKER_ROLE_ID"), "INFINITY_WORKER_ROLE_ID")
    GENESIS_WORKER_ROLE_ID: int = _require_int(os.getenv("GENESIS_WORKER_ROLE_ID"), "GENESIS_WORKER_ROLE_ID")
    WANDERER_CUSTOMER_ROLE_ID: int = _require_int(os.getenv("WANDERER_CUSTOMER_ROLE_ID"), "WANDERER_CUSTOMER_ROLE_ID")
    VOYAGER_CUSTOMER_ROLE_ID: int = _require_int(os.getenv("VOYAGER_CUSTOMER_ROLE_ID"), "VOYAGER_CUSTOMER_ROLE_ID")
    STELLAR_CUSTOMER_ROLE_ID: int = _require_int(os.getenv("STELLAR_CUSTOMER_ROLE_ID"), "STELLAR_CUSTOMER_ROLE_ID")
    NEBULA_CUSTOMER_ROLE_ID: int = _require_int(os.getenv("NEBULA_CUSTOMER_ROLE_ID"), "NEBULA_CUSTOMER_ROLE_ID")
    GALACTIC_CUSTOMER_ROLE_ID: int = _require_int(os.getenv("GALACTIC_CUSTOMER_ROLE_ID"), "GALACTIC_CUSTOMER_ROLE_ID")
    COSMIC_CUSTOMER_ROLE_ID: int = _require_int(os.getenv("COSMIC_CUSTOMER_ROLE_ID"), "COSMIC_CUSTOMER_ROLE_ID")
    CELESTIAL_CUSTOMER_ROLE_ID: int = _require_int(os.getenv("CELESTIAL_CUSTOMER_ROLE_ID"), "CELESTIAL_CUSTOMER_ROLE_ID")
    # ================= CATEGORY IDS =================
    NEW_ORDERS_CATEGORY_ID: int = _require_int(os.getenv("NEW_ORDERS_CATEGORY_ID"), "NEW_ORDERS_CATEGORY_ID")
    CLAIMED_ORDERS_CATEGORY_ID: int = _require_int(os.getenv("CLAIMED_ORDERS_CATEGORY_ID"), "CLAIMED_ORDERS_CATEGORY_ID")
    COMPLETED_ORDERS_CATEGORY_ID: int = _require_int(os.getenv("COMPLETED_ORDERS_CATEGORY_ID"), "COMPLETED_ORDERS_CATEGORY_ID")
    # ================= CHANNEL IDS =================
    WELCOME_CHANNEL_ID: int = _require_int(os.getenv("WELCOME_CHANNEL_ID"), "WELCOME_CHANNEL_ID")
    FAREWELL_CHANNEL_ID: int = _require_int(os.getenv("FAREWELL_CHANNEL_ID"), "FAREWELL_CHANNEL_ID")
    ROLE_CLAIM_CHANNEL_ID: int = _require_int(os.getenv("ROLE_CLAIM_CHANNEL_ID"), "ROLE_CLAIM_CHANNEL_ID")
    COUNTING_CHANNEL_ID: int = _require_int(os.getenv("COUNTING_CHANNEL_ID"), "COUNTING_CHANNEL_ID")
    WORD_CHAIN_CHANNEL_ID: int = _require_int(os.getenv("WORD_CHAIN_CHANNEL_ID"), "WORD_CHAIN_CHANNEL_ID")
    GUESS_NUMBER_CHANNEL_ID: int = _require_int(os.getenv("GUESS_NUMBER_CHANNEL_ID"), "GUESS_NUMBER_CHANNEL_ID")
    SCRAMBLE_WORD_CHANNEL_ID: int = _require_int(os.getenv("SCRAMBLE_WORD_CHANNEL_ID"), "SCRAMBLE_WORD_CHANNEL_ID")
    TREASURE_HUNT_CHANNEL_ID: int = _require_int(os.getenv("TREASURE_HUNT_CHANNEL_ID"), "TREASURE_HUNT_CHANNEL_ID")
    BOSS_BATTLE_CHANNEL_ID: int = _require_int(os.getenv("BOSS_BATTLE_CHANNEL_ID"), "BOSS_BATTLE_CHANNEL_ID")
    REACTION_RUSH_CHANNEL_ID: int = _require_int(os.getenv("REACTION_RUSH_CHANNEL_ID"), "REACTION_RUSH_CHANNEL_ID")
    DAILY_CHECK_IN_CHANNEL_ID: int = _require_int(os.getenv("DAILY_CHECK_IN_CHANNEL_ID"), "DAILY_CHECK_IN_CHANNEL_ID")
    MONSTER_HUNT_CHANNEL_ID: int = _require_int(os.getenv("MONSTER_HUNT_CHANNEL_ID"), "MONSTER_HUNT_CHANNEL_ID")
    GAME_LEADERBOARD_CHANNEL_ID: int = _require_int(os.getenv("GAME_LEADERBOARD_CHANNEL_ID"), "GAME_LEADERBOARD_CHANNEL_ID")
    PLACE_ORDER_CHANNEL_ID: int = _require_int(os.getenv("PLACE_ORDER_CHANNEL_ID"), "PLACE_ORDER_CHANNEL_ID")
    PRICE_CHANNEL_ID: int = _require_int(os.getenv("PRICE_CHANNEL_ID"), "PRICE_CHANNEL_ID")
    TOP_ITEM_CHANNEL_ID: int = _require_int(os.getenv("TOP_ITEM_CHANNEL_ID"), "TOP_ITEM_CHANNEL_ID")
    MARKET_STATISTIC_CHANNEL_ID: int = _require_int(os.getenv("MARKET_STATISTIC_CHANNEL_ID"), "MARKET_STATISTIC_CHANNEL_ID")
    USER_PROFILE_CHANNEL_ID: int = _require_int(os.getenv("USER_PROFILE_CHANNEL_ID"), "USER_PROFILE_CHANNEL_ID")
    MARKET_DONATION_CHANNEL_ID: int = _require_int(os.getenv("MARKET_DONATION_CHANNEL_ID"), "MARKET_DONATION_CHANNEL_ID")
    TOP_DONOR_CHANNEL_ID: int = _require_int(os.getenv("TOP_DONOR_CHANNEL_ID"), "TOP_DONOR_CHANNEL_ID")
    GIVEAWAY_CHANNEL_ID: int = _require_int(os.getenv("GIVEAWAY_CHANNEL_ID"), "GIVEAWAY_CHANNEL_ID")
    CUSTOMER_TRANSACTION_CHANNEL_ID: int = _require_int(os.getenv("CUSTOMER_TRANSACTION_CHANNEL_ID"), "CUSTOMER_TRANSACTION_CHANNEL_ID")
    RATING_MESSAGE_CHANNEL_ID: int = _require_int(os.getenv("RATING_MESSAGE_CHANNEL_ID"), "RATING_MESSAGE_CHANNEL_ID")
    TOP_SPENDING_CUSTOMER_CHANNEL_ID: int = _require_int(os.getenv("TOP_SPENDING_CUSTOMER_CHANNEL_ID"), "TOP_SPENDING_CUSTOMER_CHANNEL_ID")
    CLAIM_MESSAGE_CHANNEL_ID: int = _require_int(os.getenv("CLAIM_MESSAGE_CHANNEL_ID"), "CLAIM_MESSAGE_CHANNEL_ID")
    WORKER_TRANSACTION_CHANNEL_ID: int = _require_int(os.getenv("WORKER_TRANSACTION_CHANNEL_ID"), "WORKER_TRANSACTION_CHANNEL_ID")
    TOP_EARNING_WORKER_CHANNEL_ID: int = _require_int(os.getenv("TOP_EARNING_WORKER_CHANNEL_ID"), "TOP_EARNING_WORKER_CHANNEL_ID")
    TOP_RATED_WORKER_CHANNEL_ID: int = _require_int(os.getenv("TOP_RATED_WORKER_CHANNEL_ID"), "TOP_RATED_WORKER_CHANNEL_ID")


settings = Settings()
log.info("Environment configuration validated")
