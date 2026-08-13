"""Per-game tenant config loaded from games/<game>/config.yaml."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger("core.tenant")

GAMES_DIR = Path(__file__).resolve().parent.parent / "games"


@dataclass(frozen=True)
class ChannelConfig:
    place_order: int
    new_orders_category: int
    claimed_orders_category: int
    completed_orders_category: int
    price: int
    market_statistic: int
    user_profile: int
    claim_log: int
    activity_log: int
    worker_transaction: int
    customer_transaction: int
    top_earning_worker: int
    top_spending_customer: int
    top_item: int
    top_donor: int
    top_rated_worker: int
    rating_message: int
    donation: int
    giveaway: int
    welcome: int
    farewell: int
    role_claim: int
    game_leaderboard: int
    counting: int = 0
    word_chain: int = 0
    scramble_word: int = 0
    boss_battle: int = 0
    monster_hunt: int = 0


@dataclass(frozen=True)
class RoleConfig:
    bot_developer: int
    bank_manager: int
    moderator: int
    worker: int
    customer: int
    announcement: int
    giveaway: int
    content_notification: int
    donor_tiers: dict[str, int]
    worker_tiers: dict[str, int]
    customer_tiers: dict[str, int]


@dataclass(frozen=True)
class AssetsConfig:
    github_user: str = ""
    github_repo: str = ""
    github_branch: str = "main"
    base_path: str = ""


@dataclass(frozen=True)
class EconomyConfig:
    worker_fee_rate: float
    max_active_orders: int
    max_active_claims: int


@dataclass(frozen=True)
class GameContext:
    game: str
    guild_id: int
    db_name: str
    channels: ChannelConfig
    roles: RoleConfig
    economy: EconomyConfig
    assets: AssetsConfig


_registry: dict[int, GameContext] = {}


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_context(game: str, data: dict) -> GameContext:
    channels_raw = data.get("channels", {})
    roles_raw = data.get("roles", {})
    economy_raw = data.get("economy", {})
    assets_raw = data.get("assets", {})

    channels = ChannelConfig(
        place_order=int(channels_raw.get("place_order", 0)),
        new_orders_category=int(channels_raw.get("new_orders_category", 0)),
        claimed_orders_category=int(channels_raw.get("claimed_orders_category", 0)),
        completed_orders_category=int(channels_raw.get("completed_orders_category", 0)),
        price=int(channels_raw.get("price", 0)),
        market_statistic=int(channels_raw.get("market_statistic", 0)),
        user_profile=int(channels_raw.get("user_profile", 0)),
        claim_log=int(channels_raw.get("claim_log", 0)),
        activity_log=int(channels_raw.get("activity_log", 0)),
        worker_transaction=int(channels_raw.get("worker_transaction", 0)),
        customer_transaction=int(channels_raw.get("customer_transaction", 0)),
        top_earning_worker=int(channels_raw.get("top_earning_worker", 0)),
        top_spending_customer=int(channels_raw.get("top_spending_customer", 0)),
        top_item=int(channels_raw.get("top_item", 0)),
        top_donor=int(channels_raw.get("top_donor", 0)),
        top_rated_worker=int(channels_raw.get("top_rated_worker", 0)),
        rating_message=int(channels_raw.get("rating_message", 0)),
        donation=int(channels_raw.get("donation", 0)),
        giveaway=int(channels_raw.get("giveaway", 0)),
        welcome=int(channels_raw.get("welcome", 0)),
        farewell=int(channels_raw.get("farewell", 0)),
        role_claim=int(channels_raw.get("role_claim", 0)),
        game_leaderboard=int(channels_raw.get("game_leaderboard", 0)),
        counting=int(channels_raw.get("counting", 0)),
        word_chain=int(channels_raw.get("word_chain", 0)),
        scramble_word=int(channels_raw.get("scramble_word", 0)),
        boss_battle=int(channels_raw.get("boss_battle", 0)),
        monster_hunt=int(channels_raw.get("monster_hunt", 0)),
    )

    roles = RoleConfig(
        bot_developer=int(roles_raw.get("bot_developer", 0)),
        bank_manager=int(roles_raw.get("bank_manager", 0)),
        moderator=int(roles_raw.get("moderator", 0)),
        worker=int(roles_raw.get("worker", 0)),
        customer=int(roles_raw.get("customer", 0)),
        announcement=int(roles_raw.get("announcement", 0)),
        giveaway=int(roles_raw.get("giveaway", 0)),
        content_notification=int(roles_raw.get("content_notification", 0)),
        donor_tiers={k: int(v) for k, v in (roles_raw.get("donor_tiers") or {}).items()},
        worker_tiers={k: int(v) for k, v in (roles_raw.get("worker_tiers") or {}).items()},
        customer_tiers={k: int(v) for k, v in (roles_raw.get("customer_tiers") or {}).items()},
    )

    economy = EconomyConfig(
        worker_fee_rate=float(economy_raw.get("worker_fee_rate", 0.01)),
        max_active_orders=int(economy_raw.get("max_active_orders", 3)),
        max_active_claims=int(economy_raw.get("max_active_claims", 3)),
    )

    db_name = str(data["database"])
    raw_base = str(assets_raw.get("base_path", "")).strip().strip("/")
    if not raw_base:
        raw_base = f"assets/{db_name}"

    assets = AssetsConfig(
        github_user=str(assets_raw.get("github_user", "")),
        github_repo=str(assets_raw.get("github_repo", "")),
        github_branch=str(assets_raw.get("github_branch", "main")),
        base_path=raw_base,
    )

    return GameContext(
        game=game,
        guild_id=int(data["guild_id"]),
        db_name=db_name,
        channels=channels,
        roles=roles,
        economy=economy,
        assets=assets,
    )


def load_all_tenants() -> None:
    _registry.clear()

    if not GAMES_DIR.exists():
        log.warning("Games directory not found: %s", GAMES_DIR)
        return

    for game_dir in sorted(GAMES_DIR.iterdir()):
        if not game_dir.is_dir():
            continue

        game = game_dir.name
        config_path = game_dir / "config.yaml"

        if not config_path.exists():
            log.warning("Config skipped (file missing) | game=%s", game)
            continue

        try:
            data = _load_yaml(config_path)
            guild_id = int(data.get("guild_id", 0))
            if guild_id == 0:
                log.warning("Tenant skipped (guild_id not set) | game=%s", game)
                continue

            ctx = _parse_context(game, data)
            _registry[ctx.guild_id] = ctx
            log.info("Tenant registered | game=%s guild=%s db=%s", game, ctx.guild_id, ctx.db_name)
        except Exception:
            log.exception("Failed to load tenant | game=%s", game)


def get_context(guild_id: int) -> GameContext | None:
    return _registry.get(guild_id)


def all_contexts() -> list[GameContext]:
    return list(_registry.values())
