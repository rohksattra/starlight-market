"""Game panel embeds, battle views, and game leaderboard pagination."""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Dict, cast

import discord
from discord.ext import commands

from bot.ui.shared import ctx_from_interaction, format_utc_timestamp, set_starlight_footer
from core.tenant import GameContext, get_context
from core.time import utc_now
from models.games import (
    GAME_PANEL_TITLES,
    GAME_TITLES,
    game_title,
    game_value_label,
    GameType,
    PlayableGameType,
)
from utils.discord_safe import safe_defer, safe_edit_message, safe_respond
from utils.ui_cooldown import begin_refresh_cooldown, clear_refresh_cooldown


ATTACK_COOLDOWN_SECONDS = 10
REFRESH_COOLDOWN_SECONDS = 60
PAGE_SIZE = 25
MAX_ITEMS = 100


def _require_ctx(interaction: discord.Interaction):
    if interaction.guild is None:
        return None
    return get_context(interaction.guild.id)


def _points_short(ctx: GameContext | None) -> str:
    if ctx is None:
        return "pts"
    return ctx.brand.points_short


def counting_embed(*, question: str, ctx: GameContext | None = None) -> discord.Embed:
    sp = _points_short(ctx)
    embed = discord.Embed(
        title=GAME_PANEL_TITLES["counting"],
        description=(
            "Send the numeric answer in this channel.\n\n"
            f"## `{question}`\n\n"
            "✅ Correct:\n"
            f"• Addition/Subtraction: **+2 Counting Score** and **+2 {sp}**\n"
            f"• Multiplication/Division: **+5 Counting Score** and **+5 {sp}**\n"
            "❌ Wrong: reaction only.\n\n"
            "Use 🔄 only if the panel does not update."
        ),
        color=0xFFD700,
    )
    return set_starlight_footer(
        embed,
        ctx=ctx,
        detail=f"Last refresh: {format_utc_timestamp()}",
    )


def wordchain_embed(*, word: str, used_count: int = 0, ctx: GameContext | None = None) -> discord.Embed:
    last = word[-1].upper() if word else "?"
    embed = discord.Embed(
        title=GAME_PANEL_TITLES["wordchain"],
        description=(
            "Continue the chain by sending a word in this channel.\n\n"
            f"Current word: **{word.title()}**\n"
            f"Next word must start with: **{last}**\n\n"
            f"✅ Valid word: **+1 Word Chain Score** and **+1 {_points_short(ctx)}**.\n"
            "Rules: no repeated word and no same user twice in a row.\n\n"
            "Use 🔄 only if the panel does not update."
        ),
        color=0xFFD700,
    )
    embed.add_field(name="Used Words", value=f"{used_count:,}", inline=True)
    return set_starlight_footer(
        embed,
        ctx=ctx,
        detail=f"Last refresh: {format_utc_timestamp()}",
    )


def scramble_embed(*, scrambled: str, hint_image_url: str = "", ctx: GameContext | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=GAME_PANEL_TITLES["scramble"],
        description=(
            "Unscramble the word and send the answer in this channel.\n\n"
            f"## `{scrambled}`\n\n"
            "🖼️ The thumbnail is a hint.\n\n"
            f"✅ Correct: **+2 Scramble Score** and **+10 {_points_short(ctx)}**.\n\n"
            "Use 🔄 only if the panel does not update."
        ),
        color=0xFFD700,
    )
    if hint_image_url:
        embed.set_thumbnail(url=hint_image_url)
    return set_starlight_footer(
        embed,
        ctx=ctx,
        detail=f"Last refresh: {format_utc_timestamp()}",
    )


def battle_embed(
    *,
    game_type: PlayableGameType,
    state: Dict[str, Any],
    ctx: GameContext | None = None,
) -> discord.Embed:
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
            "Click **Attack** to deal damage.\n"
            "Use 🔄 only if the panel does not update."
        )

    embed = discord.Embed(title=title, description=body, color=0xFFD700)
    embed.add_field(
        name="Top Damage",
        value="\n".join(lines) if lines else "No damage yet.",
        inline=False,
    )
    return set_starlight_footer(
        embed,
        ctx=ctx,
        detail=f"Last refresh: {format_utc_timestamp()}",
    )


def game_leaderboard_embed(
    *,
    game_type: GameType,
    entries: list[dict[str, Any]],
    page: int,
    page_size: int,
    ctx: GameContext | None = None,
    refreshed_at: datetime | None = None,
) -> discord.Embed:
    start = page * page_size
    end = start + page_size
    sliced = entries[start:end]
    label = game_value_label(game_type, points_short=_points_short(ctx))
    lines = [
        f"***{idx}. {entry.get('name', 'Unknown')}*** — ⭐ ***{int(entry.get('value', 0)):,} {label}***"
        for idx, entry in enumerate(sliced, start=start + 1)
    ]

    embed = discord.Embed(
        title=game_title(game_type, points_name=ctx.brand.points_name if ctx else None),
        description="\n".join(lines) if lines else "⚠️ No data available.",
        color=0xFFD700,
    )
    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    if refreshed_at is None:
        refreshed_at = utc_now()
    set_starlight_footer(
        embed,
        ctx=ctx,
        detail=(
            f"Page {page + 1}/{total_pages} • "
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        ),
    )
    return embed


class _BaseGameView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self._cooldowns: Dict[int, float] = {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    def _cooldown_remaining(self, user_id: int, seconds: int) -> int:
        now = time.time()
        last_used = self._cooldowns.get(user_id)
        if last_used is None:
            self._cooldowns[user_id] = now
            return 0
        remaining = seconds - (now - last_used)
        if remaining <= 0:
            self._cooldowns[user_id] = now
            return 0
        return int(remaining)

    def _handler(self, interaction: discord.Interaction):
        from bot.handlers.games import get_game_handler

        bot = cast(commands.Bot, interaction.client)
        return get_game_handler(bot)


class CountingGameView(_BaseGameView):
    def __init__(self) -> None:
        super().__init__()
        btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id="game:counting:refresh",
        )
        btn.callback = self.refresh
        self.add_item(btn)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        ctx = _require_ctx(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        user_id = interaction.user.id
        remaining = begin_refresh_cooldown(
            self._cooldowns, user_id, seconds=REFRESH_COOLDOWN_SECONDS
        )
        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            runtime = self._handler(interaction).runtime
            state = await runtime.state(ctx, "counting") or await runtime.reset_counting(ctx)
            await safe_edit_message(
                interaction,
                embed=counting_embed(question=state["question"], ctx=ctx),
                view=self,
            )
            await safe_respond(interaction, content="✅ Counting panel refreshed.", ephemeral=True)
        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)
            await safe_respond(interaction, content="❌ Failed to refresh panel.", ephemeral=True)


class WordChainGameView(_BaseGameView):
    def __init__(self) -> None:
        super().__init__()
        btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id="game:wordchain:refresh",
        )
        btn.callback = self.refresh
        self.add_item(btn)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        ctx = _require_ctx(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        user_id = interaction.user.id
        remaining = begin_refresh_cooldown(
            self._cooldowns, user_id, seconds=REFRESH_COOLDOWN_SECONDS
        )
        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            runtime = self._handler(interaction).runtime
            state = await runtime.state(ctx, "wordchain") or await runtime.reset_wordchain(ctx)
            await safe_edit_message(
                interaction,
                embed=wordchain_embed(
                    word=state["word"],
                    used_count=int(
                        state.get("used_count", len(state.get("used_words", []))) or 0
                    ),
                    ctx=ctx,
                ),
                view=self,
            )
            await safe_respond(
                interaction, content="✅ Word Chain panel refreshed.", ephemeral=True
            )
        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)
            await safe_respond(interaction, content="❌ Failed to refresh panel.", ephemeral=True)


class ScrambleGameView(_BaseGameView):
    def __init__(self) -> None:
        super().__init__()
        btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id="game:scramble:refresh",
        )
        btn.callback = self.refresh
        self.add_item(btn)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        ctx = _require_ctx(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        user_id = interaction.user.id
        remaining = begin_refresh_cooldown(
            self._cooldowns, user_id, seconds=REFRESH_COOLDOWN_SECONDS
        )
        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            runtime = self._handler(interaction).runtime
            state = await runtime.state(ctx, "scramble") or await runtime.reset_scramble(ctx)
            await safe_edit_message(
                interaction,
                embed=scramble_embed(
                    scrambled=state["scrambled"],
                    hint_image_url=state.get("hint_image_url", ""),
                    ctx=ctx,
                ),
                view=self,
            )
            await safe_respond(
                interaction, content="✅ Scramble Word panel refreshed.", ephemeral=True
            )
        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)
            await safe_respond(interaction, content="❌ Failed to refresh panel.", ephemeral=True)


class BattleGameView(_BaseGameView):
    def __init__(self, *, game_type: PlayableGameType) -> None:
        super().__init__()
        self.game_type = game_type

        btn = discord.ui.Button(
            label="⚔️ Attack",
            style=discord.ButtonStyle.danger,
            custom_id=f"game:{game_type}:attack",
        )
        refresh = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id=f"game:{game_type}:refresh",
        )
        btn.callback = self.attack
        refresh.callback = self.refresh
        self.add_item(btn)
        self.add_item(refresh)

    async def attack(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        ctx = _require_ctx(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        remaining = self._cooldown_remaining(interaction.user.id, ATTACK_COOLDOWN_SECONDS)
        if remaining > 0:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds**.",
                ephemeral=True,
            )
            return

        result = await self._handler(interaction).runtime.attack_enemy(
            ctx,
            game_type=self.game_type,
            user_id=str(interaction.user.id),
        )
        await safe_respond(interaction, content=result["message"], ephemeral=True)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        ctx = _require_ctx(interaction)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        user_id = interaction.user.id
        remaining = begin_refresh_cooldown(
            self._cooldowns, user_id, seconds=REFRESH_COOLDOWN_SECONDS
        )
        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            state = await self._handler(interaction).runtime.state(ctx, self.game_type)
            if not state:
                clear_refresh_cooldown(self._cooldowns, user_id)
                await safe_respond(
                    interaction, content="❌ No battle state found.", ephemeral=True
                )
                return

            await safe_edit_message(
                interaction,
                embed=battle_embed(game_type=self.game_type, state=state, ctx=ctx),
                view=self,
            )
            await safe_respond(interaction, content="✅ Battle panel refreshed.", ephemeral=True)
        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)
            await safe_respond(interaction, content="❌ Failed to refresh panel.", ephemeral=True)


class GameLeaderboardPaginationView(discord.ui.View):
    def __init__(self, *, game_type: GameType, page: int = 0) -> None:
        super().__init__(timeout=None)
        self.game_type: GameType = game_type
        self.page = page
        self._cooldowns: Dict[int, float] = {}

        prefix = f"game_leaderboard:{self.game_type}"
        self.prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:prev",
        )
        self.refresh_btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id=f"{prefix}:refresh",
        )
        self.next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:next",
        )
        self.prev_btn.callback = self.prev
        self.refresh_btn.callback = self.refresh
        self.next_btn.callback = self.next
        self.add_item(self.prev_btn)
        self.add_item(self.refresh_btn)
        self.add_item(self.next_btn)

    def set_initial_state(self, *, total_items: int) -> None:
        self.prev_btn.disabled = True
        self.next_btn.disabled = total_items <= PAGE_SIZE

    def _max_page(self, *, total_items: int) -> int:
        return max(0, (total_items - 1) // PAGE_SIZE)

    def _sync_buttons(self, *, total_items: int) -> None:
        max_page = self._max_page(total_items=total_items)
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= max_page

    def _sync_page_from_message(self, interaction: discord.Interaction) -> None:
        message = interaction.message
        if message is None or not message.embeds:
            return
        footer = message.embeds[0].footer.text or ""
        match = re.search(r"Page\s+(\d+)/(\d+)", footer)
        if not match:
            return
        self.page = max(0, int(match.group(1)) - 1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    def _sync_game_type_from_interaction(self, interaction: discord.Interaction) -> None:
        data = interaction.data or {}
        custom_id = data.get("custom_id")
        if not isinstance(custom_id, str):
            return
        parts = custom_id.split(":")
        if len(parts) >= 3 and parts[1] in GAME_TITLES:
            self.game_type = cast(GameType, parts[1])

    async def _fetch_entries(self, interaction: discord.Interaction) -> list[dict]:
        from bot.handlers.games import get_game_handler

        self._sync_game_type_from_interaction(interaction)
        self._sync_page_from_message(interaction)

        ctx = _require_ctx(interaction)
        if ctx is None or interaction.guild is None:
            return []

        bot = cast(commands.Bot, interaction.client)
        return await get_game_handler(bot).fetch_game_leaderboard(
            interaction.guild,
            ctx,
            self.game_type,
        )

    async def prev(self, interaction: discord.Interaction) -> None:
        entries = await self._fetch_entries(interaction)
        if self.page > 0:
            self.page -= 1
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        user_id = interaction.user.id
        remaining = begin_refresh_cooldown(
            self._cooldowns, user_id, seconds=REFRESH_COOLDOWN_SECONDS
        )
        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            entries = await self._fetch_entries(interaction)
            self._sync_buttons(total_items=len(entries))
            await safe_edit_message(
                interaction,
                embed=game_leaderboard_embed(
                    game_type=self.game_type,
                    entries=entries,
                    page=self.page,
                    page_size=PAGE_SIZE,
                    ctx=ctx_from_interaction(interaction),
                ),
                view=self,
            )
        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)
            await safe_respond(
                interaction, content="❌ Failed to refresh leaderboard.", ephemeral=True
            )

    async def next(self, interaction: discord.Interaction) -> None:
        entries = await self._fetch_entries(interaction)
        max_page = self._max_page(total_items=len(entries))
        if self.page < max_page:
            self.page += 1
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def _update(
        self,
        interaction: discord.Interaction,
        *,
        entries: list[dict],
    ) -> None:
        await safe_edit_message(
            interaction,
            embed=game_leaderboard_embed(
                game_type=self.game_type,
                entries=entries,
                page=self.page,
                page_size=PAGE_SIZE,
                ctx=ctx_from_interaction(interaction),
            ),
            view=self,
        )
