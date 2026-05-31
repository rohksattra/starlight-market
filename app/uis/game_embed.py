from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import discord

from app.domains.game_domain import GAME_PANEL_TITLES, PlayableGameType
from app.uis.embed_footer import set_starlight_footer


def _footer(embed: discord.Embed, refreshed_at: datetime | None = None) -> discord.Embed:
    if refreshed_at is None:
        refreshed_at = datetime.utcnow()
    return set_starlight_footer(
        embed,
        detail=(
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        ),
    )


def counting_embed(*, question: str) -> discord.Embed:
    embed = discord.Embed(
        title=GAME_PANEL_TITLES["counting"],
        description=(
            "Send the numeric answer in this channel.\n\n"
            f"## `{question}`\n\n"
            "✅ Correct: **+1 Counting Score** and **+1 SP**.\n"
            "❌ Wrong: reaction only."
        ),
        color=0xFFD700,
    )
    return _footer(embed)


def wordchain_embed(*, word: str, used_count: int = 0) -> discord.Embed:
    last = word[-1].upper() if word else "?"
    embed = discord.Embed(
        title=GAME_PANEL_TITLES["wordchain"],
        description=(
            "Continue the chain by sending a word in this channel.\n\n"
            f"Current word: **{word.title()}**\n"
            f"Next word must start with: **{last}**\n\n"
            "✅ Valid word: **+1 Word Chain Score** and **+1 SP**.\n"
            "Rules: no repeated word and no same user twice in a row."
        ),
        color=0xFFD700,
    )
    embed.add_field(name="Used Words", value=f"{used_count:,}", inline=True)
    return _footer(embed)


def trivia_embed(*, question: str) -> discord.Embed:
    embed = discord.Embed(
        title=GAME_PANEL_TITLES["trivia"],
        description=(
            "Send the answer in this channel.\n\n"
            f"## {question}\n\n"
            "✅ Correct: **+1 Trivia Score** and **+10 SP**."
        ),
        color=0xFFD700,
    )
    return _footer(embed)


def guess_embed(*, active: bool = True) -> discord.Embed:
    text = (
        "Send a number from **1-1000** in this channel."
        if active
        else "Round ended — wait for staff to start a new round."
    )
    embed = discord.Embed(
        title=GAME_PANEL_TITLES["guess"],
        description=(
            f"{text}\n\n"
            "✅ Correct: **+1 Guess Score** and **+15 SP**.\n"
            "⬆️ Reaction means your guess is too low.\n"
            "⬇️ Reaction means your guess is too high."
        ),
        color=0xFFD700,
    )
    return _footer(embed)


def treasure_embed() -> discord.Embed:
    embed = discord.Embed(
        title=GAME_PANEL_TITLES["treasure"],
        description=(
            "Click **Claim Treasure** to claim a random reward.\n\n"
            "Common: **10 SP**\n"
            "Rare: **25 SP**\n"
            "Epic: **50 SP**\n"
            "Legendary: **100 SP**"
        ),
        color=0xFFD700,
    )
    return _footer(embed)


def reaction_embed(*, claimed_count: int = 0) -> discord.Embed:
    embed = discord.Embed(
        title=GAME_PANEL_TITLES["reaction"],
        description=(
            "Click as fast as possible.\n\n"
            "🥇 First: **20 SP**\n"
            "🥈 Second: **10 SP**\n"
            "🥉 Third: **5 SP**\n\n"
            f"Claimed this round: **{claimed_count}/3**\n"
            "When full, a new round starts automatically in **30 minutes**."
        ),
        color=0xFFD700,
    )
    return _footer(embed)


def scramble_embed(*, scrambled: str) -> discord.Embed:
    embed = discord.Embed(
        title=GAME_PANEL_TITLES["scramble"],
        description=(
            "Unscramble the word and send the answer in this channel.\n\n"
            f"## `{scrambled}`\n\n"
            "✅ Correct: **+1 Scramble Score** and **+10 SP**."
        ),
        color=0xFFD700,
    )
    return _footer(embed)


def daily_embed() -> discord.Embed:
    embed = discord.Embed(
        title=GAME_PANEL_TITLES["daily"],
        description=(
            "Claim your daily Starlight Points.\n\n"
            "Day 1: **10 SP**\n"
            "Day 2: **20 SP**\n"
            "Day 3: **30 SP**\n"
            "Day 4: **40 SP**\n"
            "Day 5: **50 SP**\n"
            "Day 6: **75 SP**\n"
            "Day 7+: **100 SP**"
        ),
        color=0xFFD700,
    )
    return _footer(embed)


def battle_embed(*, game_type: PlayableGameType, state: Dict[str, Any]) -> discord.Embed:
    max_hp = int(state.get("max_hp", 1) or 1)
    hp = max(0, int(state.get("hp", 0) or 0))
    alive = bool(state.get("alive", True))
    percent = int((hp / max_hp) * 100) if max_hp else 0
    bar_fill = max(0, min(10, percent // 10))
    bar = "█" * bar_fill + "░" * (10 - bar_fill)
    damage = state.get("damage") or {}
    title = GAME_PANEL_TITLES[game_type]
    name = state.get("name", "Unknown")
    emoji = state.get("emoji", "👹")

    top = sorted(damage.items(), key=lambda x: int(x[1]), reverse=True)[:5]
    lines = [f"<@{uid}> — **{int(dmg):,} dmg**" for uid, dmg in top]

    if hp <= 0 or not alive:
        auto_wait = (
            "A new enemy will appear automatically in **1 minute**."
            if game_type == "monster"
            else "A new enemy will appear automatically in **10 minutes**."
        )
        body = f"## {emoji} {name}\n🏁 **Defeated!**\n\n{auto_wait}"
    else:
        body = (
            f"## {emoji} {name}\n"
            f"HP: **{hp:,}/{max_hp:,}**\n"
            f"`{bar}` **{percent}%**\n\n"
            "Click **Attack** to deal damage."
        )

    embed = discord.Embed(
        title=title,
        description=body,
        color=0xFFD700,
    )
    embed.add_field(name="Top Damage", value="\n".join(lines) if lines else "No damage yet.", inline=False)
    return _footer(embed)
