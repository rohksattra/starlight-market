from __future__ import annotations

from unittest.mock import patch

from games.coa.seed.monsters import DEFAULT_MONSTERS as COA_MONSTERS
from games.eop.seed.monsters import DEFAULT_MONSTERS as EOP_MONSTERS
from services.games import GameService


def _names(pool: list[dict]) -> set[str]:
    return {str(row["monster_name"]) for row in pool}


def test_eop_zero_health_is_excluded() -> None:
    hunt = GameService.battle_pool(EOP_MONSTERS, game_type="monster")
    boss = GameService.battle_pool(EOP_MONSTERS, game_type="boss")
    assert "Elite Spear Goblin Rider" not in _names(hunt)
    assert "Elite Spear Goblin Rider" not in _names(boss)


def test_eop_hunt_uses_regular_mobs() -> None:
    names = _names(GameService.battle_pool(EOP_MONSTERS, game_type="monster"))
    assert names == {
        "Bandit",
        "Bat",
        "Knight",
        "Pawn",
        "Ser Camelot",
        "Ser Kael",
        "Spear Goblin",
        "Spear Goblin Rider",
        "Torch Goblin",
    }


def test_eop_boss_uses_elites_and_named() -> None:
    names = _names(GameService.battle_pool(EOP_MONSTERS, game_type="boss"))
    assert names == {
        "Elite Minotaur",
        "Elite Spear Goblin",
        "Feitan",
        "Minotaur",
        "Zubayir",
    }


COA_SKIPPED = {"Nydarax", "Spinus", "Umbra", "War Bear"}
COA_BOSSES = {
    "Ancient War Bat",
    "Cursed Totem",
    "Golem",
    "Ice Demon",
    "Mummy",
    "Nature Elder",
    "Reanimated Soul",
    "Rock Demon",
    "Shadow Demon",
}


def test_coa_zero_health_is_excluded() -> None:
    hunt = _names(GameService.battle_pool(COA_MONSTERS, game_type="monster"))
    boss = _names(GameService.battle_pool(COA_MONSTERS, game_type="boss"))
    assert COA_SKIPPED.isdisjoint(hunt)
    assert COA_SKIPPED.isdisjoint(boss)


def test_coa_hunt_uses_regular_mobs() -> None:
    names = _names(GameService.battle_pool(COA_MONSTERS, game_type="monster"))
    assert COA_BOSSES.isdisjoint(names)
    assert "Bat" in names
    assert "Chicken" in names
    assert "Anubis Elite" in names
    assert "Sandstone Golem" in names
    assert "War Bat" in names
    assert len(names) == 59


def test_coa_boss_uses_named_raids() -> None:
    assert _names(GameService.battle_pool(COA_MONSTERS, game_type="boss")) == COA_BOSSES


def test_empty_catalog_pool_is_empty() -> None:
    rows = [
        {"monster_name": "Ghost", "monster_health": 0},
        {"monster_name": "Wisp", "monster_health": 0},
    ]
    assert GameService.battle_pool(rows, game_type="monster") == []
    assert GameService.battle_pool(rows, game_type="boss") == []


def test_hunt_damage_scales_with_health() -> None:
    bat_min, bat_max = GameService.attack_damage_range(max_hp=150, game_type="monster")
    goblin_min, goblin_max = GameService.attack_damage_range(
        max_hp=8500,
        game_type="monster",
    )
    assert 1 <= bat_min < bat_max <= 40
    assert goblin_min > bat_max
    assert goblin_max < 8500


def test_boss_damage_scales_with_health() -> None:
    feitan_min, feitan_max = GameService.attack_damage_range(
        max_hp=15_000,
        game_type="boss",
    )
    minotaur_min, minotaur_max = GameService.attack_damage_range(
        max_hp=336_000,
        game_type="boss",
    )
    assert feitan_min < feitan_max < 15_000
    assert minotaur_min > feitan_max
    assert minotaur_max < 336_000


def test_attack_rewards_stay_bounded() -> None:
    hunt_sp, hunt_bonus = GameService.attack_rewards(
        dealt=150,
        max_hp=150,
        game_type="monster",
    )
    boss_sp, boss_bonus = GameService.attack_rewards(
        dealt=336_000,
        max_hp=336_000,
        game_type="boss",
    )
    assert hunt_sp == 40
    assert hunt_bonus == 25
    assert boss_sp == 400
    assert boss_bonus == 100


def test_crit_doubles_damage() -> None:
    with patch("services.games.random.random", return_value=0.049):
        damage, is_crit = GameService.apply_crit(100)
    assert is_crit is True
    assert damage == 200

    with patch("services.games.random.random", return_value=0.05):
        damage, is_crit = GameService.apply_crit(100)
    assert is_crit is False
    assert damage == 100
