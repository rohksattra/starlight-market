from __future__ import annotations

from datetime import datetime
from typing import Any, Final, Literal, TypedDict


GameType = Literal[
    "global",
    "counting",
    "wordchain",
    "guess",
    "treasure",
    "boss",
    "reaction",
    "scramble",
    "daily",
    "monster",
]

PlayableGameType = Literal[
    "counting",
    "wordchain",
    "guess",
    "treasure",
    "boss",
    "reaction",
    "scramble",
    "daily",
    "monster",
]

TypedAnswerGameType = Literal[
    "counting",
    "wordchain",
    "guess",
    "scramble",
]

TYPED_ANSWER_GAME_TYPES: Final[tuple[TypedAnswerGameType, ...]] = (
    "counting",
    "wordchain",
    "guess",
    "scramble",
)

GamePanelType = Literal["game", "leaderboard"]

GAME_TYPES: Final[tuple[PlayableGameType, ...]] = (
    "counting",
    "wordchain",
    "guess",
    "treasure",
    "boss",
    "reaction",
    "scramble",
    "daily",
    "monster",
)

LEADERBOARD_TYPES: Final[tuple[GameType, ...]] = (
    "global",
    "reaction",
    "counting",
    "guess",
    "wordchain",
    "scramble",
    "treasure",
    "monster",
    "boss",
)

GAME_SCORE_FIELDS: Final[dict[GameType, str]] = {
    "global": "starlight_points",
    "counting": "counting_score",
    "wordchain": "wordchain_score",
    "guess": "guess_score",
    "treasure": "treasure_score",
    "boss": "boss_score",
    "reaction": "reaction_score",
    "scramble": "scramble_score",
    "monster": "monster_score",
}

GAME_TITLES: Final[dict[GameType, str]] = {
    "global": "🏆 Starlight Points Leaderboard",
    "counting": "🔢 Counting Leaderboard",
    "wordchain": "📝 Word Chain Leaderboard",
    "guess": "🎲 Guess the Number Leaderboard",
    "treasure": "🎁 Treasure Hunt Leaderboard",
    "boss": "🐉 Boss Battle Leaderboard",
    "reaction": "⚡ Reaction Rush Leaderboard",
    "scramble": "🔤 Scramble Word Leaderboard",
    "monster": "👹 Monster Hunt Leaderboard",
}

GAME_PANEL_TITLES: Final[dict[PlayableGameType, str]] = {
    "counting": "🔢 Counting Challenge",
    "wordchain": "📝 Word Chain",
    "guess": "🎲 Guess the Number",
    "treasure": "🎁 Treasure Hunt",
    "boss": "🐉 Boss Battle",
    "reaction": "⚡ Reaction Rush",
    "scramble": "🔤 Scramble Word",
    "daily": "📅 Daily Check-In",
    "monster": "👹 Monster Hunt",
}

GAME_VALUE_LABELS: Final[dict[GameType, str]] = {
    "global": "SP",
    "counting": "pts",
    "wordchain": "pts",
    "guess": "pts",
    "treasure": "pts",
    "boss": "pts",
    "reaction": "pts",
    "scramble": "pts",
    "monster": "pts",
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


class GameUserState(TypedDict):
    game_type: GameType
    user_id: str
    state: dict[str, Any]
    created_at: datetime
    updated_at: datetime