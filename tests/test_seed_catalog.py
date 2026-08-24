from __future__ import annotations

from database.seed import SEED_ITEM_PRICE, item_catalog_fields, monster_catalog_fields


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
        },
    )
    assert fields == {
        "item_category": "Equipments",
        "item_image": "Heroic_Spear.png",
        "item_emoji": "🌟",
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
        "monster_health": 15000,
        "monster_image": "Feitan.gif",
    }
    assert "monster_name" not in fields
    assert "monster_id" not in fields
