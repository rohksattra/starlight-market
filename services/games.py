"""Service for community mini-games (no Discord imports)."""
from __future__ import annotations

import random
import re
from typing import Any

from core.tenant import GameContext
from database.items import ItemRepo
from database.leaderboard import LeaderboardRepo
from database.monsters import MonsterRepo
from database.users import UserRepo
from models.games import (
    BATTLE_BOSS_KILL_SP,
    BATTLE_BOSS_LAST_HIT_SP,
    BATTLE_BOSS_MIN_HEALTH,
    BATTLE_BOSS_TARGET_HITS,
    BATTLE_HUNT_KILL_SP,
    BATTLE_HUNT_LAST_HIT_SP,
    BATTLE_HUNT_TARGET_HITS,
    SCRAMBLE_WORDS,
    WORDCHAIN_SEEDS,
    GameType,
    PlayableGameType,
)
from utils.assets import item_image_url, monster_image_url


class GameService:
    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self.users = UserRepo(ctx.db_name)
        self.leaderboards = LeaderboardRepo(ctx.db_name)
        self.items = ItemRepo(ctx.db_name)
        self.monsters = MonsterRepo(ctx.db_name)

    async def add_points(
        self,
        *,
        user_id: str,
        game_type: PlayableGameType,
        score_points: int,
        market_points: int,
    ) -> None:
        await self.users.inc_game_score(
            user_id=user_id,
            game_type=game_type,
            score_points=score_points,
            market_points=market_points,
        )

    async def fetch_leaderboard(
        self,
        *,
        game_type: GameType,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return await self.leaderboards.top_game(game_type=game_type, limit=limit)

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

    def _item_image_url(self, *, item_image: str, item_category: str) -> str:
        return item_image_url(
            self.ctx,
            item_image=item_image,
            item_category=item_category,
        )

    def _monster_image_url(self, *, monster_image: str) -> str:
        return monster_image_url(self.ctx, monster_image=monster_image)

    def _brand_words(self) -> tuple[str, ...]:
        words: list[str] = []
        for part in self.ctx.brand.name.replace("-", " ").split():
            cleaned = re.sub(r"[^a-z]", "", part.lower())
            if len(cleaned) >= 4:
                words.append(cleaned)
        return tuple(words)

    async def _scramble_pool(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []

        for item in await self.items.get_all(limit=5000):
            answer = self._clean_scramble_answer(str(item.get("item_name", "")))
            if len(answer.replace(" ", "")) < 4:
                continue
            rows.append({
                "answer": answer,
                "hint_image_url": self._item_image_url(
                    item_image=str(item.get("item_image", "")),
                    item_category=str(item.get("item_category", "")),
                ),
                "source": "item",
            })

        for monster in await self.monsters.get_all(limit=5000):
            answer = self._clean_scramble_answer(str(monster.get("monster_name", "")))
            if len(answer.replace(" ", "")) < 4:
                continue
            rows.append({
                "answer": answer,
                "hint_image_url": self._monster_image_url(
                    monster_image=str(monster.get("monster_image", "")),
                ),
                "source": "monster",
            })

        if rows:
            return rows

        return [
            {
                "answer": word,
                "hint_image_url": "",
                "source": "fallback",
            }
            for word in (*SCRAMBLE_WORDS, *self._brand_words())
        ]

    async def scramble_word(self) -> dict[str, str]:
        pool = await self._scramble_pool()
        picked = random.choice(pool)
        answer = picked["answer"]
        chars = list(answer.replace(" ", ""))

        while True:
            random.shuffle(chars)
            scrambled = "".join(chars)
            if scrambled.lower() != answer.replace(" ", "").lower():
                break

        return {
            "scrambled": scrambled.upper(),
            "answer": answer.lower(),
            "hint_image_url": picked.get("hint_image_url", ""),
            "source": picked.get("source", "unknown"),
        }

    def wordchain_seed(self) -> str:
        pool = WORDCHAIN_SEEDS + self._brand_words()
        return random.choice(pool).lower()

    def monster_state(self) -> dict[str, Any]:
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
        return self._fallback_battle_state(name=name, emoji=emoji, hp=hp)

    def boss_state(self) -> dict[str, Any]:
        bosses = [
            ("Ancient Dragon", "🐉", 25000),
            ("Abyssal Leviathan", "🐲", 30000),
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
        return self._fallback_battle_state(name=name, emoji=emoji, hp=hp)

    @staticmethod
    def _fallback_battle_state(*, name: str, emoji: str, hp: int) -> dict[str, Any]:
        return {
            "name": name,
            "emoji": emoji,
            "max_hp": hp,
            "hp": hp,
            "alive": True,
            "damage": {},
            "image_url": "",
        }

    @staticmethod
    def battle_pool(
        monsters: list[dict[str, Any]],
        *,
        game_type: PlayableGameType,
        min_boss_hp: int = BATTLE_BOSS_MIN_HEALTH,
    ) -> list[dict[str, Any]]:
        ready = [
            row
            for row in monsters
            if int(row.get("monster_health") or 0) > 0
        ]
        if game_type == "boss":
            return [
                row
                for row in ready
                if int(row.get("monster_health") or 0) >= min_boss_hp
            ]
        return [
            row
            for row in ready
            if int(row.get("monster_health") or 0) < min_boss_hp
        ]

    @staticmethod
    def attack_damage_range(
        *,
        max_hp: int,
        game_type: PlayableGameType,
    ) -> tuple[int, int]:
        hits = BATTLE_BOSS_TARGET_HITS if game_type == "boss" else BATTLE_HUNT_TARGET_HITS
        average = max(1.0, max_hp / hits)
        damage_min = max(1, int(average * 0.45))
        damage_max = max(damage_min + 1, int(average * 1.55))
        return damage_min, damage_max

    @staticmethod
    def roll_attack(*, max_hp: int, game_type: PlayableGameType) -> int:
        damage_min, damage_max = GameService.attack_damage_range(
            max_hp=max_hp,
            game_type=game_type,
        )
        return random.randint(damage_min, damage_max)

    @staticmethod
    def attack_rewards(
        *,
        dealt: int,
        max_hp: int,
        game_type: PlayableGameType,
    ) -> tuple[int, int]:
        kill_sp = BATTLE_BOSS_KILL_SP if game_type == "boss" else BATTLE_HUNT_KILL_SP
        last_hit = (
            BATTLE_BOSS_LAST_HIT_SP if game_type == "boss" else BATTLE_HUNT_LAST_HIT_SP
        )
        if max_hp <= 0:
            return 1, last_hit
        sp = max(1, int(round(dealt / max_hp * kill_sp)))
        return sp, last_hit

    def _catalog_battle_state(
        self,
        monster: dict[str, Any],
        *,
        game_type: PlayableGameType,
    ) -> dict[str, Any]:
        hp = int(monster.get("monster_health") or 0)
        emoji = "🐉" if game_type == "boss" else "👹"
        return {
            "name": str(monster.get("monster_name") or "Unknown"),
            "emoji": emoji,
            "max_hp": hp,
            "hp": hp,
            "alive": True,
            "damage": {},
            "image_url": self._monster_image_url(
                monster_image=str(monster.get("monster_image") or ""),
            ),
        }

    async def battle_state(self, game_type: PlayableGameType) -> dict[str, Any]:
        rows = await self.monsters.list_with_health(min_health=1)
        pool = self.battle_pool(rows, game_type=game_type)
        if not pool:
            return self.boss_state() if game_type == "boss" else self.monster_state()
        return self._catalog_battle_state(random.choice(pool), game_type=game_type)
