from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import discord

from app.domains.game_domain import (
    SCRAMBLE_WORDS,
    TRIVIA_QUESTIONS,
    WORDCHAIN_SEEDS,
    GameType,
    PlayableGameType,
)
from app.repositories.game_repo import GameRepository
from app.repositories.leaderboard_repo import LeaderboardRepository
from app.repositories.user_repo import UserRepository


class GameService:
    def __init__(self) -> None:
        self.games = GameRepository()
        self.leaderboards = LeaderboardRepository()
        self.users = UserRepository()

    async def add_points(
        self,
        *,
        user_id: str,
        game_type: PlayableGameType,
        score_points: int,
        starlight_points: int,
    ) -> None:
        await self.users.inc_game_score(
            user_id=user_id,
            game_type=game_type,
            score_points=score_points,
            starlight_points=starlight_points,
        )

    async def fetch_leaderboard(self, *, game_type: GameType, limit: int = 100) -> List[Dict[str, Any]]:
        return await self.leaderboards.top_game(game_type=game_type, limit=limit)

    async def hydrate_user_names(
        self,
        *,
        guild: discord.Guild | None,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        for row in rows:
            name = f"<@{row['id']}>"
            if guild is not None:
                member = guild.get_member(int(row["id"]))
                if member:
                    name = member.display_name
            row["name"] = name
        return rows

    def counting_question(self) -> tuple[str, int]:
        a = random.randint(1, 100)
        b = random.randint(1, 100)
        op = random.choice(["+", "-", "*", "/"])

        if op == "/":
            a *= b

        if op == "+":
            answer = a + b
        elif op == "-":
            answer = a - b
        elif op == "*":
            answer = a * b
        else:
            answer = a // b

        return f"{a} {op} {b}", answer

    def trivia_question(self) -> Dict[str, str]:
        return dict(random.choice(TRIVIA_QUESTIONS))

    def scramble_word(self) -> Dict[str, str]:
        answer = random.choice(SCRAMBLE_WORDS)
        chars = list(answer)
        while True:
            random.shuffle(chars)
            scrambled = "".join(chars)
            if scrambled.lower() != answer.lower():
                break
        return {"scrambled": scrambled.upper(), "answer": answer.lower()}

    def wordchain_seed(self) -> str:
        return random.choice(WORDCHAIN_SEEDS).lower()

    def guess_number(self) -> int:
        return random.randint(1, 1000)

    def treasure_reward(self) -> Dict[str, Any]:
        roll = random.random()
        if roll < 0.01:
            return {"rarity": "Legendary", "emoji": "🌟", "points": 100}
        if roll < 0.10:
            return {"rarity": "Epic", "emoji": "💎", "points": 50}
        if roll < 0.30:
            return {"rarity": "Rare", "emoji": "✨", "points": 25}
        return {"rarity": "Common", "emoji": "🪙", "points": 10}

    def monster_state(self) -> Dict[str, Any]:
        monsters = [
            ("Goblin", "👹", 800),
            ("Stone Golem", "🗿", 1200),
            ("Shadow Wolf", "🐺", 1000),
            ("Crystal Slime", "🟦", 900),
        ]
        name, emoji, hp = random.choice(monsters)
        return {
            "name": name,
            "emoji": emoji,
            "max_hp": hp,
            "hp": hp,
            "alive": True,
            "damage": {},
        }

    def boss_state(self) -> Dict[str, Any]:
        bosses = [
            ("Ancient Dragon", "🐉", 25000),
            ("Starlight Leviathan", "🐲", 30000),
            ("Astral Behemoth", "🦖", 28000),
        ]
        name, emoji, hp = random.choice(bosses)
        return {
            "name": name,
            "emoji": emoji,
            "max_hp": hp,
            "hp": hp,
            "alive": True,
            "damage": {},
        }

    def reaction_round(self) -> Dict[str, Any]:
        return {
            "round_id": str(random.randint(100000, 999999)),
            "claimed_user_ids": [],
            "rewards": [20, 10, 5],
        }

    async def claim_daily(self, *, user_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        start_of_today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

        doc = await self.games.get_user_state(game_type="daily", user_id=user_id)
        state = doc.get("state", {}) if doc else {}
        last_claimed_at = state.get("last_claimed_at")
        streak = int(state.get("streak", 0) or 0)

        last_dt: datetime | None = None
        if isinstance(last_claimed_at, datetime):
            last_dt = last_claimed_at
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)

        if last_dt and last_dt >= start_of_today:
            raise ValueError("Daily reward already claimed today")

        if last_dt and last_dt.date() == (now - timedelta(days=1)).date():
            streak += 1
        else:
            streak = 1

        capped = min(streak, 7)
        reward_table = {1: 10, 2: 20, 3: 30, 4: 40, 5: 50, 6: 75, 7: 100}
        reward = reward_table[capped]

        reserved = await self.games.user_states.update_one(
            {
                "game_type": "daily",
                "user_id": user_id,
                "$or": [
                    {"state.last_claimed_at": {"$exists": False}},
                    {"state.last_claimed_at": {"$lt": start_of_today}},
                ],
            },
            {
                "$set": {
                    "game_type": "daily",
                    "user_id": user_id,
                    "state": {"last_claimed_at": now, "streak": streak},
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        if reserved.modified_count == 0 and reserved.upserted_id is None:
            raise ValueError("Daily reward already claimed today")

        await self.add_points(
            user_id=user_id,
            game_type="daily",
            score_points=1,
            starlight_points=reward,
        )

        return {"reward": reward, "streak": streak}
