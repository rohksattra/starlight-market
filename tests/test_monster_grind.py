from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from bot.ui.monster_grind import DISCLAIMER, grind_estimate_embed
from database.seed import load_game_catalog
from services.monster_grind import (
    DropEstimate,
    GrindEstimate,
    MonsterGrindService,
    ParsedDrop,
    estimate_drops,
    format_chance_denom,
    format_qty_range,
    parse_drop_rolls,
    parse_monster_drops,
)


def _run(coro):
    return asyncio.run(coro)


def _anubis_drop() -> str:
    _items, monsters = load_game_catalog("coa")
    by_name = {row["monster_name"]: row for row in monsters}
    return str(by_name["Anubis"]["monster_drop"])


def _mummy_drop() -> str:
    _items, monsters = load_game_catalog("coa")
    by_name = {row["monster_name"]: row for row in monsters}
    return str(by_name["Mummy"]["monster_drop"])


def test_parse_and_format_independent_anubis() -> None:
    drops = parse_monster_drops(_anubis_drop())
    by_name = {drop.name: drop for drop in drops}
    assert by_name["Flask of Life"] == ParsedDrop("Flask of Life", 3.0, 1, 3)
    assert by_name["Health Flask"] == ParsedDrop("Health Flask", 6.0, 2, 5)
    assert by_name["Gold Key"] == ParsedDrop("Gold Key", 2261.0, 1, 1)

    rows = {drop.name: (lo, hi) for drop, lo, hi in estimate_drops(drops, 1000)}
    assert rows["Flask of Life"] == (1000 / 3, 1000)
    assert rows["Health Flask"] == ((1000 / 6) * 2, (1000 / 6) * 5)
    assert format_qty_range(*rows["Flask of Life"]) == "333–1,000"
    assert format_qty_range(*rows["Health Flask"]) == "333–833"
    assert format_qty_range(*rows["Gold Key"]) == "<1"
    assert format_qty_range(*rows["Red Key"]) == "1"
    assert [drop.name for drop, _lo, _hi in estimate_drops(drops, 1000)][0] == "Flask of Life"


def test_parse_skips_none_and_defaults_missing_qty() -> None:
    drops = parse_monster_drops(_mummy_drop())
    names = [drop.name for drop in drops]
    assert "Mummy Pet" not in names
    amulet = next(drop for drop in drops if drop.name == "Ancient Amulet")
    assert amulet.chance_denom == 288
    assert amulet.qty_min == amulet.qty_max == 1
    assert parse_monster_drops("") == []
    assert parse_monster_drops("None") == []
    assert format_chance_denom(1.2469) == "1/1.2469"
    assert format_chance_denom(3) == "1/3"
    assert parse_drop_rolls("Drops 4 items upon death") == 4
    assert parse_drop_rolls("Drops 2 items upon death") == 2
    assert parse_drop_rolls("") == 1

    war_bat = parse_monster_drops("Potion (1/1) (5-10), Bat Amulet (1/45) (1)")
    rows = {drop.name: (lo, hi) for drop, lo, hi in estimate_drops(war_bat, 1000, drop_rolls=4)}
    assert rows["Potion"] == (20_000, 40_000)
    assert rows["Bat Amulet"] == (1000 * 4 / 45, 1000 * 4 / 45)


def test_grind_estimate_embed_matches_price_list_style() -> None:
    estimate = GrindEstimate(
        monster_name="Anubis",
        monster_level=90,
        monster_emoji="<:anubis:1>",
        monster_image="anubis.png",
        monster_drop_note="",
        drop_rolls=1,
        kill_count=1000,
        total_exp=4_000_000,
        total_gold=57_000,
        drops=[
            DropEstimate("Flask of Life", "<:fol:1>", 3, 1, 3, 1000 / 3, 1000),
            DropEstimate("Gold Key", "", 2261, 1, 1, 1000 / 2261, 1000 / 2261),
        ],
    )
    embed = grind_estimate_embed(estimate)
    assert embed.title == "⚔️ Grind Estimate — ***Anubis***"
    desc = embed.description or ""
    assert "From ***1,000*** kills of <:anubis:1> ***Anubis*** (Lv 90):" in desc
    assert "🟡 EXP ***4,000,000*** · 🪙 Gold ***57,000***" in desc
    assert "***<:fol:1> Flask of Life*** (1/3) — ***333–1,000***" in desc
    assert "***🌟 Gold Key*** (1/2261) — ***<1***" in desc
    assert DISCLAIMER in desc
    assert embed.footer.text == "🌟 Starlight Market • Grind Estimate"


def test_grind_estimate_embed_empty_drops_and_note() -> None:
    estimate = GrindEstimate(
        monster_name="Brown Snake",
        monster_level=120,
        monster_emoji="🌟",
        monster_image="",
        monster_drop_note="Drops 4 items upon death",
        drop_rolls=4,
        kill_count=10,
        total_exp=10_000,
        total_gold=600,
        drops=[],
    )
    desc = grind_estimate_embed(estimate).description or ""
    assert "⚠️ No drop data." in desc
    assert desc.index("⚠️ No drop data.") < desc.index("Estimates are multiplied by 4")
    assert "*Drops 4 items upon death. Estimates are multiplied by 4.*" in desc
    assert "🟡 EXP" in desc.split("⚠️ No drop data.")[0]


def test_monster_grind_service_estimate() -> None:
    ctx = MagicMock()
    ctx.db_name = "test"
    with patch("services.monster_grind.MonsterRepo"):
        service = MonsterGrindService(ctx)
    service.monsters = AsyncMock()
    service.monsters.get_by_name.return_value = {
        "monster_name": "Anubis",
        "monster_level": 90,
        "monster_emoji": "<:anubis:1>",
        "monster_image": "anubis.png",
        "monster_drop_note": "",
        "monster_exp": 4000,
        "monster_gold": 57,
        "monster_drop": "Flask of Life (1/3) (1-3), Gold Key (1/2261) (1)",
    }
    cached_items = [
        {"item_name": "Flask of Life", "item_emoji": "<:fol:1>"},
        {"item_name": "Gold Key", "item_emoji": ""},
    ]

    with patch(
        "services.monster_grind.catalog_cache.items",
        AsyncMock(return_value=cached_items),
    ):
        estimate = _run(service.estimate(monster_name="Anubis", kill_count=1000))
    assert estimate.total_exp == 4_000_000
    assert estimate.total_gold == 57_000
    assert estimate.drop_rolls == 1
    assert estimate.drops[0].name == "Flask of Life"
    assert estimate.drops[0].emoji == "<:fol:1>"
    assert estimate.drops[1].emoji == "🌟"

    service.monsters.get_by_name.return_value["monster_drop_note"] = "Drops 4 items upon death"
    service.monsters.get_by_name.return_value["monster_drop"] = "Potion (1/1) (5-10)"
    with patch(
        "services.monster_grind.catalog_cache.items",
        AsyncMock(return_value=cached_items),
    ):
        multiplied = _run(service.estimate(monster_name="War Bat", kill_count=1000))
    assert multiplied.drop_rolls == 4
    assert multiplied.drops[0].expected_min == 20_000
    assert multiplied.drops[0].expected_max == 40_000

    with patch(
        "services.monster_grind.catalog_cache.monsters",
        AsyncMock(
            return_value=[
                {"monster_name": "Anubis", "monster_level": 90},
                {"monster_name": "Anubis Elite", "monster_level": 110},
                {"monster_name": "Ice Slime", "monster_level": 21},
            ]
        ),
    ):
        labels = _run(service.autocomplete("anu"))
    assert [value for _label, value in labels] == ["Anubis", "Anubis Elite"]
