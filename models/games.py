"""Game types, score fields, and panel titles for community mini-games."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Final, Literal, TypedDict

PlayableGameType = Literal[
    "counting",
    "wordchain",
    "scramble",
    "monster",
    "boss",
]

TypedAnswerGameType = Literal[
    "counting",
    "wordchain",
    "scramble",
]

GameType = Literal[
    "global",
    "counting",
    "wordchain",
    "scramble",
    "monster",
    "boss",
]

GamePanelType = Literal["game", "leaderboard"]

PLAYABLE_GAME_TYPES: Final[tuple[PlayableGameType, ...]] = (
    "counting",
    "wordchain",
    "scramble",
    "monster",
    "boss",
)

TYPED_ANSWER_GAME_TYPES: Final[tuple[TypedAnswerGameType, ...]] = (
    "counting",
    "wordchain",
    "scramble",
)

BATTLE_GAME_TYPES: Final[tuple[PlayableGameType, PlayableGameType]] = (
    "monster",
    "boss",
)

LEADERBOARD_TYPES: Final[tuple[GameType, ...]] = (
    "global",
    "counting",
    "wordchain",
    "scramble",
    "monster",
    "boss",
)

GAME_SCORE_FIELDS: Final[dict[GameType, str]] = {
    "global": "starlight_points",
    "counting": "counting_score",
    "wordchain": "wordchain_score",
    "scramble": "scramble_score",
    "monster": "monster_score",
    "boss": "boss_score",
}

GAME_TITLES: Final[dict[GameType, str]] = {
    "global": "🏆 Starlight Points Leaderboard",
    "counting": "🔢 Counting Leaderboard",
    "wordchain": "📝 Word Chain Leaderboard",
    "scramble": "🔤 Scramble Word Leaderboard",
    "monster": "👹 Monster Hunt Leaderboard",
    "boss": "🐉 Boss Battle Leaderboard",
}

GAME_PANEL_TITLES: Final[dict[PlayableGameType, str]] = {
    "counting": "🔢 Counting Challenge",
    "wordchain": "📝 Word Chain",
    "scramble": "🔤 Scramble Word",
    "monster": "👹 Monster Hunt",
    "boss": "🐉 Boss Battle",
}

GAME_VALUE_LABELS: Final[dict[GameType, str]] = {
    "global": "SP",
    "counting": "pts",
    "wordchain": "pts",
    "scramble": "pts",
    "monster": "pts",
    "boss": "pts",
}

BATTLE_AUTO_NEW_ENEMY_SECONDS: Final[dict[PlayableGameType, int]] = {
    "monster": 60,
    "boss": 10 * 60,
}

SCRAMBLE_WORDS: Final[tuple[str, ...]] = (
    "market",
    "starlight",
    "worker",
    "customer",
    "treasure",
    "dragon",
    "monster",
    "leaderboard",
    "counting",
    "discord",
)

WORDCHAIN_SEEDS: Final[tuple[str, ...]] = (
    "market",
    "treasure",
    "dragon",
    "starlight",
    "monster",
    "worker",
    "customer",
)


class GamePanel(TypedDict):
    panel_type: GamePanelType
    game_type: GameType
    channel_id: str
    message_id: str
    created_at: datetime
    updated_at: datetime


class GameStateDocument(TypedDict):
    game_type: GameType
    state: dict[str, Any]
    created_at: datetime
    updated_at: datetime
