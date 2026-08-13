# Starsistant (Starlight Market V2)

Multi-tenant Discord marketplace bot. Discord username: **Starsistant**. Shop brands stay per game: **Starlight Market** (CoA) and **Praxia Market** (EoP).

**Model:** 1 Discord guild = 1 game = 1 MongoDB database.

| Game | Brand | Mongo DB | Config |
|------|-------|----------|--------|
| Curse of Aros (CoA) | Starlight Market / SP | `curseofaros` | `games/coa/config.yaml` |
| Empire of Praxia (EoP) | Praxia Market / PP | `empireofpraxia` | `games/eop/config.yaml` |

Secrets live only in `.env` (`DISCORD_TOKEN`, `MONGO_URI`). Channel/role IDs live in per-game YAML. Never commit `.env` — it is listed in `.gitignore`. Copy `.env.example` for a blank template.

---

## Run locally

From the project root:

```bash
pip install -r requirements.txt
python main.py
```

Do not run the legacy bot and this bot against the same live guild at the same time.

Health endpoint (PaaS keepalive): `GET /` → `200 starlight-v2:ok` when Discord is ready and Mongo answers ping; `503` otherwise (`discord:not-ready` or `mongo:unreachable`). Port from `PORT`, default `10000`.

Tests:

```bash
python -m pytest tests -q
```

---

## Go-live checklist

1. Push GitHub assets to:
   - `assets/curseofaros/items/{category}/{file}`
   - `assets/curseofaros/monsters/{file}`
   - (EoP) `assets/empireofpraxia/...` when those files exist
2. Confirm `.env` has `DISCORD_TOKEN` + `MONGO_URI` (Atlas). Do not commit this file.
3. Confirm CoA data is in MongoDB database `curseofaros`.
4. EoP catalog seed starts with `item_price: 0`. Set live prices with `/update-item-price`, then refresh boards with `!mprice`. Orders reject a price of 0.
5. Smoke test: `!morder` / place order → claim → `/income` → profile → price panel → one mini-game.

---

## Architecture

```
.
├── main.py                 # Entry
├── core/                   # settings, tenant, bot, startup, views, web
├── games/
│   ├── coa/config.yaml     # Live CoA IDs + economy + assets
│   └── eop/config.yaml     # Live EoP IDs + economy + assets
├── models/                 # TypedDicts / enums
├── database/               # Mongo repos (db_name per call)
├── services/               # Business logic (NO discord imports)
├── bot/
│   ├── commands/           # Thin cogs
│   ├── handlers/           # Interaction wiring
│   ├── ui/                 # Embeds, buttons, modals
│   ├── events/             # Join/leave, game messages
│   └── tier_sync.py
├── tests/                  # pytest (claim, economy, tier)
└── utils/                  # Logger, permissions, assets URLs, etc.
```

**Data flow:** command/event → handler → service → database. Discord I/O stays in `bot/ui` + handlers.

**Tenant resolve:** `get_context(guild.id)` — never hardcode guild/channel IDs in code.

| Layer | CoA | Empire of Praxia |
|-------|-----|------------------|
| Config | `games/coa/config.yaml` | `games/eop/config.yaml` |
| Mongo DB | `curseofaros` | `empireofpraxia` |
| Assets | `assets/curseofaros/...` | `assets/empireofpraxia/...` |
| Load rule | Live guild | Live guild (`guild_id` in YAML) |

Do not rename Mongo DB names, GitHub asset repo `starlight-market`, or persistent `custom_id` prefixes (`sl_gv:`, `sl_gvw:`, `sl_rc:`). Those are game/data identities, not the Discord username.

---

## Legacy vs V2 parity

### Verdict

**In-scope feature parity: complete** for CoA cutover. All marketplace, staff, economy, and kept community features exist in V2.

### Intentionally removed (legacy only)

| Game | Legacy key |
|------|------------|
| Daily Check-In | `daily` |
| Reaction Rush | `reaction` |
| Guess the Number | `guess` |
| Treasure Hunt | `treasure` |

Residual Mongo data for those games was cleaned from `curseofaros` before go-live.

### Intentionally added in V2

| Feature | Notes |
|---------|--------|
| Multi-tenant config | Per-game YAML + DB |
| `activity_log` channel | Plain-text staff audit trail |
| Shared asset helper | `utils/assets.py` per `base_path` |

### Command parity (kept)

**Slash (OM = Bot Dev / Bank Manager · Staff = OM + Moderator)**

| Command | Access | Status |
|---------|--------|--------|
| `/claim` `/unclaim` | Worker | OK |
| `/income` | OM | OK |
| `/custom-order` | OM | OK |
| `/order-item-price-update` | OM | OK |
| `/order-item-quantity-update` | OM | OK |
| `/order-customer-update` | OM | OK |
| `/force-claim` `/force-unclaim` | OM | OK |
| `/paid` `/spent` | OM | OK |
| `/donation` | OM | OK |
| `/profile` | Public | OK |
| `/giveaway` | OM | OK |
| `/delete-message` | Staff | OK |
| `/update-member-role` | OM | OK |
| `/update-category-name` | OM | OK |
| `/update-item-name` | OM | OK |
| `/update-item-price` | OM | OK |
| `/game-panel` | Staff | OK (5 games only) |
| `/leaderboard-panel` | Staff | OK |
| `/leaderboard-panel-all` | Staff | OK |

**Prefix**

| Command | Access | Status |
|---------|--------|--------|
| `!morder` | OM | OK |
| `!mcancel` | OM | OK |
| `!mprice` | OM | OK |
| `!mroles` | OM | OK |
| `!mrules` | OM | OK |
| `!mstat` | Public | OK |
| `!mclaimable` | Public | OK |
| `!mme` | Public | OK |
| `!minfo` | Public | OK |
| `!mcleanupdata` | OM | OK |

**Context menu:** Calculate Worker Payment (OM) — OK.

### Kept mini-games

| Game | Channel config key | Interaction |
|------|--------------------|-------------|
| Counting | `counting` | Typed answers |
| Word Chain | `word_chain` | Typed answers |
| Scramble Word | `scramble_word` | Typed answers + image hint |
| Monster Hunt | `monster_hunt` | Attack button (~60s respawn) |
| Boss Battle | `boss_battle` | Attack button (~10m respawn) |

---

## Roles & economy

### Base roles (self-claim via `!mroles`)

Worker, Customer, Announcement, Giveaway, Content notification.

### Staff

- **OM:** Bot Developer, Bank Manager — income, catalog, donations, force-claim, panels seed.
- **Staff:** OM + Moderator — `/delete-message`, game/leaderboard panels.

### Tiers (thresholds in `services/tiers.py`, role IDs in YAML)

- **Donor** Relic → Astralis — donation gold → monthly coupon caps (1–12).
- **Worker** Explorer → Genesis — income → max claim orders + claim capacity.
- **Customer** Wanderer → Celestial — spent → max active orders + order capacity.

Defaults (below tier): 3 orders / 5 000 capacity (worker & customer).

**Worker fee:** `economy.worker_fee_rate` (CoA `0.01` → worker keeps **99%**).

**Donor coupon:** 0.5% discount on order create when coupons remain; refunded on cancel.

---

## Order lifecycle

1. Staff posts `!morder` → customers use **Order Now** (category → item → qty).
2. Private order channel under **New Orders**; claim panel for workers.
3. Claims move channel toward **Claimed**; staff `/income` (worker) logs tx + rating prompt.
4. When worker side completes → pickup embed → **Completed** category.
5. `/income` (customer) → **Close Order** button.
6. Staff may `!mcancel` with confirm.

Logging channels: `claim_log`, `worker_transaction`, `customer_transaction`, `rating_message`, `activity_log`, `donation`.

News channels: transaction posts are auto-published when the channel is an Announcement channel.

---

## Assets

GitHub raw URLs (CoA example):

```
https://github.com/<user>/<repo>/raw/refs/heads/<branch>/assets/curseofaros/items/<category>/<file>
https://github.com/<user>/<repo>/raw/refs/heads/<branch>/assets/curseofaros/monsters/<file>
```

Configured in YAML:

```yaml
assets:
  github_user: rohksattra
  github_repo: starlight-market
  github_branch: main
  base_path: assets/curseofaros
```

Default if `base_path` omitted: `assets/<database_name>`.

---

## Catalog seed

On every bot start/redeploy, bootstrap seeds items/monsters from `games/<game>/seed/`. Missing rows are inserted; existing rows are skipped (including price). To change a live price, use `/update-item-price` — do not rely on re-seeding.

---

## Empire of Praxia

Tenant config and seed catalog are in place. Remaining operational steps:

1. Confirm `games/eop/config.yaml` IDs match the live server.
2. Set catalog prices with `/update-item-price` (seed prices are 0 until then).
3. Post `!mprice` so price boards pick up the new values.
4. Push `assets/empireofpraxia/...` and match `assets.github_*` in YAML.
5. Smoke the same order flow as CoA.

---

## Operations notes

- **Persistent views** restored on boot via `core/view_registry.py` (orders, prices, LBs, games, role claim, giveaways).
- **Tier sync** on member join and after income / paid / spent / donation / `/update-member-role`.
- **Giveaways** recover and continue timers after restart.
- **Battle games** recover auto-reset timers after restart.
- **Statistics** document is ensured per tenant on boot.
- **Transactions** retry up to 3 times on `TransientTransactionError` / `UnknownTransactionCommitResult`.
- `!mcleanupdata` deletes closed/canceled orders, transactions, and ratings older than 365 days via repos (not raw collection access).
- Keep Mongo DB `starlightmarket` as read-only backup until V2 is verified in production; V2 reads/writes `curseofaros` (and `empireofpraxia` for EoP).
- Do not reintroduce business logic into cogs or Discord imports into `services/`.

---

## Quick reference — panel seed commands

| Goal | Command |
|------|---------|
| Order entry | `!morder` |
| Price boards | `!mprice` |
| Role claim | `!mroles` |
| Market rules | `!mrules` |
| Market stats | `!mstat` |
| All leaderboards | `/leaderboard-panel-all` |
| One game panel | `/game-panel` |
| Bot help | `!minfo` |

---

## Requirements

- Python 3.11+ recommended (tested with 3.14 locally)
- See `requirements.txt` (`discord.py`, `motor`, `pymongo`, `python-dotenv`, `pyyaml`, `pytest`)
