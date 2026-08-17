# Starsistant

Discord marketplace bot for **Curse of Aros** (Starlight Market) and **Empire of Praxia** (Praxia Market).

One guild = one game = one MongoDB database. Discord username is **Starsistant**; shop names stay per game.

## Setup

1. Copy `.env.example` to `.env` and set `DISCORD_TOKEN` and `MONGO_URI`.
2. Fill channel, role, economy, and asset settings in `games/<game>/config.yaml`.
3. Install and run:

```bash
pip install -r requirements.txt
python main.py
```

Do not commit `.env`. Python 3.11+ is recommended.

```bash
python -m pytest tests -q
```

Hosted deploys expose `GET /` on `PORT` (default `10000`): `200` when Discord is ready and Mongo answers ping, otherwise `503`.

## Layout

```
main.py          entry
core/            settings, tenant, bot, startup
games/           per-game YAML + catalog seed
bot/             commands, handlers, UI, events
services/        business logic (no Discord imports)
database/        Mongo repositories
tests/
```

Flow: command or event → handler → service → database. Resolve a guild with `get_context(guild.id)` — do not hardcode Discord IDs in code.

## Features

- Orders, claims, income, catalog, and price boards
- Worker / customer / donor tiers and coupons
- Giveaways, role claim, rules, and pickup guide
- Mini-games: counting, word chain, scramble, monster hunt, boss battle
- Persistent panels reconnect after restart

Staff seed panels with `!morder`, `!mprice`, `!mroles`, `!mrules`, `!mpickup`, `!mstat`, `/game-panel`, and `/leaderboard-panel`. Use `!minfo` for the in-Discord command list.

Item and monster images are loaded from GitHub raw URLs set under `assets` in each game YAML (`base_path` defaults to `assets/<database_name>`). Catalog rows in `games/<game>/seed/` are inserted on boot if missing; existing prices are not overwritten. Set live prices with `/update-item-price` (`0` marks an item Unavailable).
