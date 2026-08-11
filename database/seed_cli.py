"""CLI: seed items/monsters for a game tenant.

Usage (from starlight_v2/):
  python -m database.seed_cli --game coa
  python -m database.seed_cli --game eop
  python -m database.seed_cli --game eop --db empireoffraxia
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure starlight_v2 is on sys.path when run as module
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.tenant import GAMES_DIR, load_all_tenants, all_contexts  # noqa: E402
from database.seed import seed_game  # noqa: E402
from utils.logger import setup_logging  # noqa: E402

log = logging.getLogger("database.seed_cli")


def _db_name_for_game(game: str) -> str | None:
    # Prefer live tenant registry if guild is configured
    load_all_tenants()
    for ctx in all_contexts():
        if ctx.game == game:
            return ctx.db_name

    # Fallback: read yaml even when guild_id == 0
    path = GAMES_DIR / game / "config.yaml"
    if not path.exists():
        return None
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    db = data.get("database")
    return str(db) if db else None


async def _run(game: str, db_name: str | None) -> int:
    resolved = db_name or _db_name_for_game(game)
    if not resolved:
        log.error("Unknown game or missing database | game=%s", game)
        return 1

    result = await seed_game(game, resolved)
    print(
        f"Seeded {game} → {resolved} | "
        f"items_new={result['items_inserted']} "
        f"monsters_new={result['monsters_inserted']}"
    )
    return 0


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Seed Starlight V2 game catalogs")
    parser.add_argument("--game", required=True, choices=["coa", "eop"], help="Game folder under games/")
    parser.add_argument("--db", default=None, help="Override Mongo database name")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.game, args.db)))


if __name__ == "__main__":
    main()
