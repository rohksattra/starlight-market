# Starlight Market V2

Multi-tenant Discord marketplace bot for **Curse of Aros (CoA)** and future games (e.g. **Empire of Praxia**).

**Model:** 1 Discord guild = 1 game = 1 MongoDB database.

---

## Go-live checklist

1. Push GitHub assets to:
   - `assets/curseofaros/items/{category}/{file}`
   - `assets/curseofaros/monsters/{file}`
2. Confirm `starlight_v2/.env` has `DISCORD_TOKEN` + `MONGO_URI` (Atlas).
3. Confirm CoA data is in MongoDB database `curseofaros` (already migrated).
4. **Do not** run legacy bot + V2 against live traffic at the same time.
5. From `starlight_v2/`:
   ```bash
   pip install -r requirements.txt
   python main.py
   ```
6. Smoke test: `!order` / place order → claim → `/income` → profile → price panel → one mini-game.

Health endpoint (PaaS keepalive): `GET /` → `starlight-v2:ok` (port from `PORT`, default `10000`).

---

## Architecture

```
starlight_v2/
├── main.py                 # Entry
├── core/                   # settings, tenant, bot, startup, views, web
├── games/
│   ├── coa/config.yaml     # Live CoA IDs + economy + assets
│   └── eop/config.yaml     # Stub (guild_id: 0 → skipped)
├── models/                 # TypedDicts / enums
├── database/               # Mongo repos (db_name per call)
├── services/               # Business logic (NO discord imports)
├── bot/
│   ├── commands/           # Thin cogs
│   ├── handlers/           # Interaction wiring
│   ├── ui/                 # Embeds, buttons, modals
│   ├── events/             # Join/leave, game messages
│   └── tier_sync.py
└── utils/                  # Logger, permissions, assets URLs, etc.
```

**Data flow:** command/event → handler → service → database. Discord I/O stays in `bot/ui` + handlers.

**Tenant resolve:** `get_context(guild.id)` — never hardcode guild/channel IDs in code.

| Layer | CoA | Empire of Praxia |
|-------|-----|------------------|
| Config | `games/coa/config.yaml` | `games/eop/config.yaml` |
| Mongo DB | `curseofaros` | `empireoffraxia` |
| Assets | `assets/curseofaros/...` | `assets/empireoffraxia/...` |
| Load rule | Live guild | `guild_id: 0` → not loaded |

Secrets only in `.env`: `DISCORD_TOKEN`, `MONGO_URI`. Channel/role IDs live in per-game YAML.

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
| `!order` | OM | OK |
| `!cancel` | OM | OK |
| `!price` | OM | OK |
| `!roles` | OM | OK |
| `!mstat` | Public | OK |
| `!claimable` | Public | OK |
| `!me` | Public | OK |
| `!slinfo` | Public | OK |
| `!cleanupdata` | OM | OK |

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

### Base roles (self-claim via `!roles`)

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

1. Staff posts `!order` → customers use **Order Now** (category → item → qty).
2. Private order channel under **New Orders**; claim panel for workers.
3. Claims move channel toward **Claimed**; staff `/income` (worker) logs tx + rating prompt.
4. When worker side completes → pickup embed → **Completed** category.
5. `/income` (customer) → **Close Order** button.
6. Staff may `!cancel` with confirm.

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

## Catalog seed (new tenant / empty DB)

```bash
cd starlight_v2
python -m database.seed_cli --game coa   # or eop
```

Inserts items/monsters from `games/<game>/seed/` only when missing (safe re-run). CoA already has migrated catalog — seed not required for cutover.

---

## Enabling Empire of Praxia (later)

1. Create Discord server + mirror channel/role layout.
2. Fill all IDs in `games/eop/config.yaml` (`guild_id != 0`).
3. Fill `games/eop/seed/items.py` (+ monsters).
4. `python -m database.seed_cli --game eop`
5. Set `assets.github_*` and push `assets/empireoffraxia/...`.
6. Restart bot.

---

## Operations notes

- **Persistent views** restored on boot via `core/view_registry.py` (orders, prices, LBs, games, role claim, giveaways).
- **Tier sync** on member join and after income / paid / spent / donation / `/update-member-role`.
- **Giveaways** recover and continue timers after restart.
- **Battle games** recover auto-reset timers after restart.
- Keep Mongo DB `starlightmarket` as read-only backup until V2 is verified in production; V2 reads/writes `curseofaros` only.
- Do not reintroduce business logic into cogs or Discord imports into `services/`.

---

## Quick reference — panel seed commands

| Goal | Command |
|------|---------|
| Order entry | `!order` |
| Price boards | `!price` |
| Role claim | `!roles` |
| Market stats | `!mstat` |
| All leaderboards | `/leaderboard-panel-all` |
| One game panel | `/game-panel` |
| Bot help | `!slinfo` |

---

## Requirements

- Python 3.11+ recommended (tested with 3.14 locally)
- See `requirements.txt` (`discord.py`, `motor`, `pymongo`, `python-dotenv`, `pyyaml`)
