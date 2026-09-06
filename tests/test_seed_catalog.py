from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from database.seed import (
    SEED_ITEM_PRICE,
    catalog_fields_match,
    item_catalog_fields,
    load_game_catalog,
    monster_catalog_fields,
)


def test_new_items_always_seed_price_zero() -> None:
    assert SEED_ITEM_PRICE == 0


def test_item_catalog_fields_skip_name_and_price() -> None:
    fields = item_catalog_fields(
        "Equipments",
        {
            "item_name": "Heroic Spear",
            "item_price": 999,
            "item_image": "Heroic_Spear.png",
            "item_emoji": "",
            "is_sell": True,
        },
    )
    assert fields == {
        "item_category": "Equipments",
        "item_image": "Heroic_Spear.png",
        "item_emoji": "🌟",
        "is_sell": True,
    }
    assert "item_name" not in fields
    assert "item_price" not in fields
    assert "item_sold" not in fields


def test_monster_catalog_fields_skip_name() -> None:
    fields = monster_catalog_fields(
        {
            "monster_name": "Feitan",
            "monster_level": "76",
            "monster_health": 15000,
            "monster_image": "Feitan.gif",
        },
    )
    assert fields == {
        "monster_level": 76,
        "monster_type": "",
        "monster_health": 15000,
        "monster_exp": 0,
        "monster_gold": 0,
        "monster_drop": "",
        "monster_drop_note": "",
        "monster_image": "Feitan.gif",
        "monster_emoji": "",
    }
    assert "monster_name" not in fields
    assert "monster_id" not in fields


def test_item_catalog_fields_default_is_sell_true() -> None:
    fields = item_catalog_fields(
        "Tools",
        {"item_name": "Titanium Axe", "item_image": "Titanium_Axe.png"},
    )
    assert fields["is_sell"] is True
    assert item_catalog_fields("Tools", {"is_sell": False})["is_sell"] is False


def test_seed_items_are_sellable() -> None:
    for game in ("coa", "eop"):
        items, _monsters = load_game_catalog(game)
        rows = [row for category in items.values() for row in category]
        assert rows
        assert all(row.get("is_sell") is True for row in rows)


def test_coa_monster_seed_uses_new_schema() -> None:
    _items, monsters = load_game_catalog("coa")
    by_name = {row["monster_name"]: row for row in monsters}
    assert by_name["Shadow Flame"]["monster_health"] == 3675
    assert by_name["War Bat"]["monster_type"] == "Boss"
    assert by_name["Cursed Totem"]["monster_type"] == "Minion"
    assert by_name["War Bear"]["monster_type"] == "Boss"
    assert {"Nydarax (50)", "Nydarax (100)", "Nydarax (200)"} <= set(by_name)
    assert "Nydarax" not in by_name
    assert by_name["War Bat"]["monster_drop_note"] == "Drops 4 items upon death"


def test_catalog_fields_match_skips_equal_rows() -> None:
    fields = item_catalog_fields(
        "Potions",
        {"item_image": "potion.png", "item_emoji": "🧪", "is_sell": True},
    )
    assert catalog_fields_match(fields, fields)
    without_sell = dict(fields)
    without_sell.pop("is_sell")
    assert catalog_fields_match(without_sell, fields)
    changed = dict(fields)
    changed["item_emoji"] = "🌟"
    assert not catalog_fields_match(changed, fields)

    monster = monster_catalog_fields(
        {"monster_level": 90, "monster_health": 3300, "monster_exp": 4000, "monster_gold": 57}
    )
    assert catalog_fields_match({"monster_level": "90", "monster_health": 3300, "monster_exp": 4000, "monster_gold": 57, "monster_type": "", "monster_drop": "", "monster_drop_note": "", "monster_image": "", "monster_emoji": ""}, monster)


def test_seed_items_skips_unchanged_and_inserts_missing() -> None:
    import asyncio

    from database.seed import item_catalog_fields, seed_items

    existing_fields = item_catalog_fields(
        "Potions",
        {"item_image": "potion.png", "item_emoji": "🧪", "is_sell": True},
    )
    existing_fields["item_name"] = "Potion"
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[existing_fields])
    items = MagicMock()
    items.find.return_value = cursor
    items.update_one = AsyncMock(
        return_value=MagicMock(upserted_id="new", modified_count=0)
    )
    db = MagicMock(items=items)

    async def body() -> None:
        with patch("database.seed.get_db", return_value=db):
            result = await seed_items(
                "db",
                {
                    "Potions": [
                        {
                            "item_name": "Potion",
                            "item_image": "potion.png",
                            "item_emoji": "🧪",
                            "is_sell": True,
                        },
                        {
                            "item_name": "New Flask",
                            "item_image": "flask.png",
                            "item_emoji": "",
                            "is_sell": True,
                        },
                    ]
                },
            )
        assert result == {"inserted": 1, "updated": 0}
        assert items.update_one.await_count == 1
        assert items.update_one.await_args.args[0] == {"item_name": "New Flask"}

    asyncio.run(body())
