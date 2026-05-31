from __future__ import annotations

from typing import Dict

from core.config import settings
from app.domains.game_domain import TYPED_ANSWER_GAME_TYPES, PlayableGameType, TypedAnswerGameType


REACTION_AUTO_RESET_SECONDS = 30 * 60

BATTLE_GAME_TYPES: tuple[PlayableGameType, PlayableGameType] = ("monster", "boss")
BATTLE_AUTO_NEW_ENEMY_SECONDS: Dict[PlayableGameType, int] = {
    "monster": 60,
    "boss": 10 * 60,
}

PLAYABLE_GAME_CHANNEL_IDS: Dict[PlayableGameType, int] = {
    "counting": settings.COUNTING_CHANNEL_ID,
    "wordchain": settings.WORD_CHAIN_CHANNEL_ID,
    "trivia": settings.TRIVIA_CHANNEL_ID,
    "guess": settings.GUESS_NUMBER_CHANNEL_ID,
    "scramble": settings.SCRAMBLE_WORD_CHANNEL_ID,
    "treasure": settings.TREASURE_HUNT_CHANNEL_ID,
    "boss": settings.BOSS_BATTLE_CHANNEL_ID,
    "reaction": settings.REACTION_RUSH_CHANNEL_ID,
    "daily": settings.DAILY_CHECK_IN_CHANNEL_ID,
    "monster": settings.MONSTER_HUNT_CHANNEL_ID,
}

TYPED_ANSWER_CHANNEL_MAP: Dict[int, TypedAnswerGameType] = {
    PLAYABLE_GAME_CHANNEL_IDS[game_type]: game_type
    for game_type in TYPED_ANSWER_GAME_TYPES
}
