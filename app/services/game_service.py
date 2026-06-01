from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import discord

from app.domains.game_domain import (
    SCRAMBLE_WORDS,
    WORDCHAIN_SEEDS,
    GameType,
    PlayableGameType,
)
from app.repositories.game_repo import GameRepository
from app.repositories.item_repo import ItemRepository
from app.repositories.leaderboard_repo import LeaderboardRepository
from app.repositories.user_repo import UserRepository


class GameService:
    def __init__(self) -> None:
        self.games = GameRepository()
        self.items = ItemRepository()
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

    async def fetch_leaderboard(
        self,
        *,
        game_type: GameType,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self.leaderboards.top_game(
            game_type=game_type,
            limit=limit,
        )

    async def hydrate_user_names(
        self,
        *,
        guild: discord.Guild | None,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        for row in rows:
            name = "Unknown"

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

    def _clean_scramble_answer(self, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value.strip().lower())
        cleaned = re.sub(r"[^a-z0-9 ]", "", cleaned)
        return cleaned

    async def _scramble_pool(self) -> List[str]:
        items = await self.items.get_all(limit=5000)

        words = [
            self._clean_scramble_answer(str(item.get("item_name", "")))
            for item in items
        ]

        words = [
            word
            for word in words
            if len(word.replace(" ", "")) >= 4
        ]

        if words:
            return words

        return list(SCRAMBLE_WORDS)

    async def scramble_word(self) -> Dict[str, str]:
        pool = await self._scramble_pool()
        answer = random.choice(pool)
        chars = list(answer.replace(" ", ""))

        while True:
            random.shuffle(chars)
            scrambled = "".join(chars)

            if scrambled.lower() != answer.replace(" ", "").lower():
                break

        return {
            "scrambled": scrambled.upper(),
            "answer": answer.lower(),
        }

    def wordchain_seed(self) -> str:
        return random.choice(WORDCHAIN_SEEDS).lower()

    def guess_number(self) -> int:
        return random.randint(1, 1000)

    def treasure_reward(self) -> Dict[str, Any]:
        roll = random.random()

        if roll < 0.01:
            return {
                "rarity": "Legendary",
                "emoji": "🌟",
                "score": 20,
                "points": 100,
            }

        if roll < 0.10:
            return {
                "rarity": "Epic",
                "emoji": "💎",
                "score": 10,
                "points": 50,
            }

        if roll < 0.30:
            return {
                "rarity": "Rare",
                "emoji": "✨",
                "score": 5,
                "points": 25,
            }

        return {
            "rarity": "Common",
            "emoji": "🪙",
            "score": 2,
            "points": 10,
        }

    def monster_state(self) -> Dict[str, Any]:
        monsters = [
            ("Goblin", "👹", 800),
            ("Stone Golem", "🗿", 1200),
            ("Shadow Wolf", "🐺", 1000),
            ("Crystal Slime", "🟦", 900),
            ("Cursed Bat", "🦇", 750),
            ("Wild Boar", "🐗", 950),
            ("Venom Spider", "🕷️", 850),
            ("Forest Troll", "🧌", 1400),
            ("Flame Imp", "🔥", 1000),
            ("Ice Wraith", "❄️", 1100),
            ("Bone Knight", "💀", 1300),
            ("Mushroom Beast", "🍄", 900),
            ("Thunder Lizard", "🦎", 1250),
            ("Dark Mimic", "🎁", 1150),
            ("Rogue Sentinel", "🛡️", 1500),
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
            ("Void Reaper", "☠️", 32000),
            ("Celestial Hydra", "🐍", 35000),
            ("Infernal Titan", "🔥", 34000),
            ("Frost Colossus", "❄️", 31000),
            ("Eclipse Serpent", "🌑", 33000),
            ("Obsidian Golem", "🗿", 29000),
            ("Storm Phoenix", "🦅", 30000),
            ("Abyss Kraken", "🐙", 36000),
            ("Lunar Chimera", "🌙", 31500),
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

    async def claim_daily(
        self,
        *,
        user_id: str,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)

        today_key = now.date().isoformat()
        yesterday_key = (now.date() - timedelta(days=1)).isoformat()

        doc = await self.games.get_user_state(
            game_type="daily",
            user_id=user_id,
        )

        state = doc.get("state", {}) if doc else {}

        last_claim_date = state.get("last_claim_date")
        streak = int(state.get("streak", 0) or 0)

        if last_claim_date == today_key:
            raise ValueError("Daily reward already claimed today")

        if last_claim_date == yesterday_key:
            streak += 1
        else:
            streak = 1

        reward_table = {
            1: 10,
            2: 20,
            3: 30,
            4: 40,
            5: 50,
            6: 75,
            7: 100,
        }

        reward = reward_table[min(streak, 7)]

        claimed = await self.games.try_claim_daily(
            user_id=user_id,
            today_key=today_key,
            streak=streak,
            reward=reward,
            now=now,
        )

        if not claimed:
            raise ValueError("Daily reward already claimed today")

        await self.add_points(
            user_id=user_id,
            game_type="daily",
            score_points=0,
            starlight_points=reward,
        )

        return {
            "reward": reward,
            "streak": streak,
        }