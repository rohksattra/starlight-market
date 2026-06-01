from __future__ import annotations

import time
from typing import Any, Dict, cast

import discord
from discord.ext import commands

from app.domains.game_domain import PlayableGameType
from app.uis.game_embed import (
    battle_embed,
    counting_embed,
    daily_embed,
    guess_embed,
    reaction_embed,
    scramble_embed,
    wordchain_embed,
)
from utils.interaction_safe import safe_defer, safe_edit_message, safe_respond
from utils.ui_cooldown import begin_refresh_cooldown, clear_refresh_cooldown


BUTTON_COOLDOWN_SECONDS = 10
ATTACK_COOLDOWN_SECONDS = 10
TREASURE_COOLDOWN_SECONDS = 5 * 60
REFRESH_COOLDOWN_SECONDS = 60


def _format_cooldown_wait(remaining: int) -> str:
    if remaining >= 60:
        minutes = remaining // 60
        seconds = remaining % 60

        if seconds:
            return f"**{minutes} minute(s) {seconds} second(s)**"

        return f"**{minutes} minute(s)**"

    return f"**{remaining} seconds**"


class _BaseGameView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self._cooldowns: Dict[int, float] = {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    def _cooldown_remaining(
        self,
        user_id: int,
        seconds: int,
    ) -> int:
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

    def _game_cog(self, interaction: discord.Interaction) -> Any:
        bot = cast(commands.Bot, interaction.client)
        cog = bot.get_cog("Game")

        if cog is None:
            raise RuntimeError("Game cog missing")

        return cog


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

        user_id = interaction.user.id

        remaining = begin_refresh_cooldown(
            self._cooldowns,
            user_id,
            seconds=REFRESH_COOLDOWN_SECONDS,
        )

        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            cog = self._game_cog(interaction)

            state = await cog.runtime.state("counting")
            if not state:
                state = await cog.runtime.reset_counting()

            await safe_edit_message(
                interaction,
                embed=counting_embed(question=state["question"]),
                view=self,
            )

            await safe_respond(
                interaction,
                content="✅ Counting panel refreshed.",
                ephemeral=True,
            )

        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)

            await safe_respond(
                interaction,
                content="❌ Failed to refresh panel.",
                ephemeral=True,
            )


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

        user_id = interaction.user.id

        remaining = begin_refresh_cooldown(
            self._cooldowns,
            user_id,
            seconds=REFRESH_COOLDOWN_SECONDS,
        )

        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            cog = self._game_cog(interaction)

            state = await cog.runtime.state("wordchain")
            if not state:
                state = await cog.runtime.reset_wordchain()

            await safe_edit_message(
                interaction,
                embed=wordchain_embed(
                    word=state["word"],
                    used_count=len(state.get("used_words", [])),
                ),
                view=self,
            )

            await safe_respond(
                interaction,
                content="✅ Word Chain panel refreshed.",
                ephemeral=True,
            )

        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)

            await safe_respond(
                interaction,
                content="❌ Failed to refresh panel.",
                ephemeral=True,
            )


class GuessGameView(_BaseGameView):
    def __init__(self) -> None:
        super().__init__()

        btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id="game:guess:refresh",
        )

        btn.callback = self.refresh
        self.add_item(btn)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)

        user_id = interaction.user.id

        remaining = begin_refresh_cooldown(
            self._cooldowns,
            user_id,
            seconds=REFRESH_COOLDOWN_SECONDS,
        )

        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            cog = self._game_cog(interaction)

            state = await cog.runtime.state("guess")
            if not state:
                state = await cog.runtime.reset_guess()

            await safe_edit_message(
                interaction,
                embed=guess_embed(active=bool(state.get("active", True))),
                view=self,
            )

            await safe_respond(
                interaction,
                content="✅ Guess the Number panel refreshed.",
                ephemeral=True,
            )

        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)

            await safe_respond(
                interaction,
                content="❌ Failed to refresh panel.",
                ephemeral=True,
            )


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

        user_id = interaction.user.id

        remaining = begin_refresh_cooldown(
            self._cooldowns,
            user_id,
            seconds=REFRESH_COOLDOWN_SECONDS,
        )

        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            cog = self._game_cog(interaction)

            state = await cog.runtime.state("scramble")
            if not state:
                state = await cog.runtime.reset_scramble()

            await safe_edit_message(
                interaction,
                embed=scramble_embed(scrambled=state["scrambled"]),
                view=self,
            )

            await safe_respond(
                interaction,
                content="✅ Scramble Word panel refreshed.",
                ephemeral=True,
            )

        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)

            await safe_respond(
                interaction,
                content="❌ Failed to refresh panel.",
                ephemeral=True,
            )


class TreasureGameView(_BaseGameView):
    def __init__(self) -> None:
        super().__init__()

        btn = discord.ui.Button(
            label="🎁 Claim Treasure",
            style=discord.ButtonStyle.success,
            custom_id="game:treasure:claim",
        )

        btn.callback = self.claim
        self.add_item(btn)

    async def claim(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)

        remaining = self._cooldown_remaining(
            interaction.user.id,
            TREASURE_COOLDOWN_SECONDS,
        )

        if remaining > 0:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait {_format_cooldown_wait(remaining)} before claiming again.",
                ephemeral=True,
            )
            return

        cog = self._game_cog(interaction)

        reward = await cog.runtime.claim_treasure(
            user_id=str(interaction.user.id),
        )

        await safe_respond(
            interaction,
            content=(
                f"{reward['emoji']} You found a **{reward['rarity']} Treasure** "
                f"and gained **+{reward['score']} Score** and **+{reward['points']} SP**."
            ),
            ephemeral=True,
        )


class ReactionRushGameView(_BaseGameView):
    def __init__(
        self,
        *,
        click_disabled: bool = False,
    ) -> None:
        super().__init__()

        self.click_btn = discord.ui.Button(
            label="⚡ Click!",
            style=discord.ButtonStyle.danger,
            custom_id="game:reaction:click",
            disabled=click_disabled,
        )

        refresh = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id="game:reaction:refresh",
        )

        self.click_btn.callback = self.click
        refresh.callback = self.refresh

        self.add_item(self.click_btn)
        self.add_item(refresh)

    def _sync_click_button(
        self,
        *,
        claimed_count: int,
    ) -> None:
        self.click_btn.disabled = claimed_count >= 3

    async def click(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)

        cog = self._game_cog(interaction)

        try:
            result = await cog.runtime.claim_reaction(
                user_id=str(interaction.user.id),
            )

        except ValueError as exc:
            await safe_respond(
                interaction,
                content=f"❌ {exc}",
                ephemeral=True,
            )
            return

        claimed_count = int(result["claimed_count"])

        self._sync_click_button(
            claimed_count=claimed_count,
        )

        await safe_edit_message(
            interaction,
            embed=reaction_embed(claimed_count=claimed_count),
            view=self,
        )

        if claimed_count >= 3:
            await safe_respond(
                interaction,
                content=(
                    f"⚡ Rank **#{result['rank']}**! "
                    f"You gained **+{result['score']} Score** and **+{result['points']} SP**.\n"
                    "🏁 Round full — a new round will start automatically in **30 minutes**."
                ),
                ephemeral=True,
            )
            return

        await safe_respond(
            interaction,
            content=(
                f"⚡ Rank **#{result['rank']}**! "
                f"You gained **+{result['score']} Score** and **+{result['points']} SP**."
            ),
            ephemeral=True,
        )

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)

        user_id = interaction.user.id

        remaining = begin_refresh_cooldown(
            self._cooldowns,
            user_id,
            seconds=REFRESH_COOLDOWN_SECONDS,
        )

        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            cog = self._game_cog(interaction)
            state = await cog.runtime.state("reaction")
            claimed_count = len(state.get("claimed_user_ids", [])) if state else 0

            self._sync_click_button(
                claimed_count=claimed_count,
            )

            await safe_edit_message(
                interaction,
                embed=reaction_embed(claimed_count=claimed_count),
                view=self,
            )

            await safe_respond(
                interaction,
                content="✅ Reaction Rush panel refreshed.",
                ephemeral=True,
            )

        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)

            await safe_respond(
                interaction,
                content="❌ Failed to refresh panel.",
                ephemeral=True,
            )


class DailyGameView(_BaseGameView):
    def __init__(self) -> None:
        super().__init__()

        claim_btn = discord.ui.Button(
            label="📅 Claim Daily",
            style=discord.ButtonStyle.success,
            custom_id="game:daily:claim",
        )

        refresh_btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.secondary,
            custom_id="game:daily:refresh",
        )

        claim_btn.callback = self.claim
        refresh_btn.callback = self.refresh

        self.add_item(claim_btn)
        self.add_item(refresh_btn)

    async def claim(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)

        cog = self._game_cog(interaction)

        try:
            result = await cog.runtime.claim_daily(
                user_id=str(interaction.user.id),
            )

        except ValueError as exc:
            await safe_respond(
                interaction,
                content=f"⏳ {exc}",
                ephemeral=True,
            )
            return

        await safe_edit_message(
            interaction,
            embed=daily_embed(),
            view=self,
        )

        await safe_respond(
            interaction,
            content=(
                "✅ **Daily Check-In Claimed!**\n"
                f"🔥 Streak: **{result['streak']} day(s)**\n"
                f"🌟 Reward: **+{result['reward']:,} SP**"
            ),
            ephemeral=True,
        )

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)

        user_id = interaction.user.id

        remaining = begin_refresh_cooldown(
            self._cooldowns,
            user_id,
            seconds=REFRESH_COOLDOWN_SECONDS,
        )

        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            await safe_edit_message(
                interaction,
                embed=daily_embed(),
                view=self,
            )

            await safe_respond(
                interaction,
                content="✅ Daily Check-In panel refreshed.",
                ephemeral=True,
            )

        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)

            await safe_respond(
                interaction,
                content="❌ Failed to refresh panel.",
                ephemeral=True,
            )


class BattleGameView(_BaseGameView):
    def __init__(
        self,
        *,
        game_type: PlayableGameType,
    ) -> None:
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

        remaining = self._cooldown_remaining(
            interaction.user.id,
            ATTACK_COOLDOWN_SECONDS,
        )

        if remaining > 0:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds**.",
                ephemeral=True,
            )
            return

        cog = self._game_cog(interaction)

        result = await cog.runtime.attack_enemy(
            game_type=self.game_type,
            user_id=str(interaction.user.id),
        )

        await safe_respond(
            interaction,
            content=result["message"],
            ephemeral=True,
        )

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)

        user_id = interaction.user.id

        remaining = begin_refresh_cooldown(
            self._cooldowns,
            user_id,
            seconds=REFRESH_COOLDOWN_SECONDS,
        )

        if remaining is not None:
            await safe_respond(
                interaction,
                content=f"⏳ Please wait **{remaining} seconds** before refreshing again.",
                ephemeral=True,
            )
            return

        try:
            cog = self._game_cog(interaction)

            state = await cog.runtime.state(self.game_type)
            if not state:
                clear_refresh_cooldown(self._cooldowns, user_id)

                await safe_respond(
                    interaction,
                    content="❌ No battle state found.",
                    ephemeral=True,
                )
                return

            await safe_edit_message(
                interaction,
                embed=battle_embed(
                    game_type=self.game_type,
                    state=state,
                ),
                view=self,
            )

            await safe_respond(
                interaction,
                content="✅ Battle panel refreshed.",
                ephemeral=True,
            )

        except Exception:
            clear_refresh_cooldown(self._cooldowns, user_id)

            await safe_respond(
                interaction,
                content="❌ Failed to refresh panel.",
                ephemeral=True,
            )