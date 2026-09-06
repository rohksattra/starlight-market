from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.catalog_cache import (
    clear,
    emoji_by_id,
    emoji_by_name,
    filter_items,
    invalidate,
    item_map,
    items,
    monsters,
)


def _run(coro):
    return asyncio.run(coro)


def setup_function() -> None:
    clear()


def test_filter_items_caps_and_category() -> None:
    rows = [
        {"item_id": "1", "item_name": "Health Flask", "item_category": "Potions", "item_emoji": "a"},
        {"item_id": "2", "item_name": "Flask of Life", "item_category": "Potions", "item_emoji": "b"},
        {"item_id": "3", "item_name": "Iron Sword", "item_category": "Weapons", "item_emoji": "c"},
    ]
    found = filter_items(rows, "flask", limit=25)
    assert [row["item_name"] for row in found] == ["Health Flask", "Flask of Life"]
    swords = filter_items(rows, "", limit=25, category="Weapons")
    assert [row["item_id"] for row in swords] == ["3"]
    assert emoji_by_name(rows)["health flask"] == "a"
    assert emoji_by_id(rows)["1"] == "a"


def test_items_cache_loads_once_then_invalidates() -> None:
    repo = AsyncMock()
    repo.get_all.return_value = [
        {"item_id": "1", "item_name": "Potion", "item_price": 10, "item_emoji": "", "item_category": "Potions"},
    ]
    with patch("services.catalog_cache.ItemRepo", return_value=repo):
        first = _run(items("db-a"))
        second = _run(items("db-a"))
    assert first[0]["item_emoji"] == "🌟"
    assert first == second
    assert _run(item_map("db-a"))["1"]["item_name"] == "Potion"
    assert repo.get_all.await_count == 1

    invalidate("db-a")
    repo.get_all.return_value = [
        {"item_id": "1", "item_name": "Potion", "item_price": 12, "item_emoji": "🧪", "item_category": "Potions"},
    ]
    with patch("services.catalog_cache.ItemRepo", return_value=repo):
        third = _run(items("db-a"))
    assert third[0]["item_price"] == 12
    assert repo.get_all.await_count == 2


def test_item_map_lookup_is_by_id() -> None:
    repo = AsyncMock()
    repo.get_all.return_value = [
        {"item_id": "9", "item_name": "Ore", "item_price": 1, "item_emoji": "🪨", "item_category": "Ores"},
    ]
    with patch("services.catalog_cache.ItemRepo", return_value=repo):
        found = _run(item_map("db-b"))
    assert found["9"]["item_emoji"] == "🪨"


def test_get_item_emoji_uses_item_map() -> None:
    from services.items import ItemService

    ctx = MagicMock()
    ctx.db_name = "db-a"
    with patch("services.items.ItemRepo"):
        service = ItemService(ctx)
    with patch(
        "services.items.item_map",
        AsyncMock(return_value={"1": {"item_emoji": "🧪"}}),
    ):
        assert _run(service.get_item_emoji("1")) == "🧪"
        assert _run(service.get_item_emoji("missing")) == "🌟"


def test_monsters_cache_loads_once() -> None:
    repo = AsyncMock()
    repo.get_all.return_value = [{"monster_name": "Anubis", "monster_level": 90, "monster_health": 3300}]
    with patch("services.catalog_cache.MonsterRepo", return_value=repo):
        _run(monsters("db-a"))
        _run(monsters("db-a"))
    assert repo.get_all.await_count == 1
