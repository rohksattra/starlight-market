from __future__ import annotations

from datetime import datetime
from typing import List

import discord
from discord.ext import commands

from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.discord.giveaway_runtime import get_giveaway_runtime
from app.services.giveaway_service import GiveawayService, finalize_lock
from app.views.giveaway_winner_view import GiveawayWinnerSelectView


class GiveawayHandler:
    def __init__(self) -> None:
        self.svc = GiveawayService()
        self.runtime = get_giveaway_runtime()

    def _is_staff(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        return has_any_role(interaction.user, ORDER_MANAGEMENT_ROLES)

    async def register_persistent_views(self, bot: commands.Bot) -> int:
        return await self.runtime.register_persistent_views(bot)

    async def recover_stale_giveaways(self, bot: commands.Bot) -> None:
        await self.runtime.recover_stale_giveaways(bot)

    async def handle_join(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Use this in the server.", ephemeral=True)
            return

        if interaction.user.bot:
            await interaction.response.send_message("❌ Bots cannot join.", ephemeral=True)
            return

        try:
            added = await self.svc.join(
                giveaway_id=giveaway_id,
                user_id=str(interaction.user.id),
                now=datetime.utcnow(),
            )
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        if added:
            await interaction.response.send_message("✅ You have joined the giveaway.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ You are already entered.", ephemeral=True)

    async def handle_participants(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        doc = await self.svc.get_by_id(giveaway_id)
        if not doc:
            await interaction.response.send_message("❌ Giveaway not found.", ephemeral=True)
            return

        guild = interaction.guild
        pids: List[str] = list(doc.get("participant_user_ids") or [])
        if not pids:
            await interaction.response.send_message("No participants yet.", ephemeral=True)
            return

        lines: List[str] = []
        for i, uid in enumerate(pids[:40], start=1):
            name = f"<@{uid}>"
            if guild:
                member = guild.get_member(int(uid))
                if member:
                    name = member.display_name
            lines.append(f"{i}. {name}")

        extra = len(pids) - 40
        body = "\n".join(lines)
        if extra > 0:
            body += f"\n… and **{extra}** more."
        if len(body) > 1800:
            body = body[:1800] + "\n… *(list truncated)*"

        await interaction.response.send_message(
            f"**Participants ({len(pids)})**\n{body}",
            ephemeral=True,
        )

    async def handle_refresh(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            await self.svc.require_open(giveaway_id)
        except ValueError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        bot = interaction.client
        await self.runtime.finalize_giveaway(bot, giveaway_id)

        doc = await self.svc.get_by_id(giveaway_id)
        if not doc:
            await interaction.followup.send("❌ Giveaway not found.", ephemeral=True)
            return

        await self.runtime.edit_main_panel(
            bot=bot,
            giveaway_id=giveaway_id,
            guild=interaction.guild,
            doc=doc,
        )
        await interaction.followup.send("✅ Giveaway panel updated.", ephemeral=True)

    async def handle_cancel_giveaway(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self._is_staff(interaction):
            await interaction.followup.send(
                "❌ Only Bot Developer / Bank Manager can cancel giveaway.",
                ephemeral=True,
            )
            return

        async with finalize_lock(giveaway_id):
            try:
                doc = await self.svc.cancel_open(
                    giveaway_id=giveaway_id,
                    moderator_id=str(interaction.user.id),
                    now=datetime.utcnow(),
                )
            except ValueError as exc:
                await interaction.followup.send(f"❌ {exc}", ephemeral=True)
                return

            await self.runtime.edit_main_panel(
                bot=interaction.client,
                giveaway_id=giveaway_id,
                guild=interaction.guild,
                doc=doc,
            )

        await interaction.followup.send("✅ Giveaway cancelled.", ephemeral=True)

    async def handle_reroll_all(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self._is_staff(interaction):
            await interaction.followup.send(
                "❌ Only Bot Developer / Bank Manager can reroll.",
                ephemeral=True,
            )
            return

        async with finalize_lock(giveaway_id):
            try:
                winners = await self.svc.reroll_all_unclaimed(
                    giveaway_id=giveaway_id,
                    moderator_id=str(interaction.user.id),
                    now=datetime.utcnow(),
                )
            except ValueError as exc:
                await interaction.followup.send(f"❌ {exc}", ephemeral=True)
                return

            await self.runtime.edit_winner_announcement(
                bot=interaction.client,
                giveaway_id=giveaway_id,
                guild=interaction.guild,
                winner_user_ids=winners,
            )

        await interaction.followup.send("✅ Unclaimed winners rerolled.", ephemeral=True)

    async def handle_reroll_partial_prompt(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        if not self._is_staff(interaction):
            await interaction.response.send_message(
                "❌ Only Bot Developer / Bank Manager can reroll.",
                ephemeral=True,
            )
            return

        try:
            doc = await self.svc.require_completed(giveaway_id)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        winners = self.svc.unclaimed_winners(doc)
        if not winners:
            await interaction.response.send_message(
                "❌ No unclaimed winners available to reroll.",
                ephemeral=True,
            )
            return

        view = GiveawayWinnerSelectView(
            giveaway_id,
            winners[:25],
            interaction.guild,
            mode="reroll",
        )
        await interaction.response.send_message(
            "Choose winner(s) you want to reroll.",
            view=view,
            ephemeral=True,
        )

    async def handle_reroll_partial_selected(
        self,
        interaction: discord.Interaction,
        giveaway_id: str,
        user_ids: list[str],
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self._is_staff(interaction):
            await interaction.followup.send(
                "❌ Only Bot Developer / Bank Manager can reroll.",
                ephemeral=True,
            )
            return

        async with finalize_lock(giveaway_id):
            try:
                winners = await self.svc.reroll_selected(
                    giveaway_id=giveaway_id,
                    selected_winner_ids=user_ids,
                    moderator_id=str(interaction.user.id),
                    now=datetime.utcnow(),
                )
            except ValueError as exc:
                await interaction.followup.send(f"❌ {exc}", ephemeral=True)
                return

            await self.runtime.edit_winner_announcement(
                bot=interaction.client,
                giveaway_id=giveaway_id,
                guild=interaction.guild,
                winner_user_ids=winners,
            )

        await interaction.followup.send("✅ Selected winner(s) rerolled.", ephemeral=True)

    async def handle_mark_claimed_prompt(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        if not self._is_staff(interaction):
            await interaction.response.send_message(
                "❌ Only Bot Developer / Bank Manager can use this.",
                ephemeral=True,
            )
            return

        try:
            doc = await self.svc.require_completed(giveaway_id)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        winners = self.svc.unclaimed_winners(doc)
        if not winners:
            await interaction.response.send_message("❌ All winners already claimed.", ephemeral=True)
            return

        view = GiveawayWinnerSelectView(
            giveaway_id,
            winners[:25],
            interaction.guild,
            mode="claim",
        )
        await interaction.response.send_message(
            "Choose winner(s) to mark as claimed.",
            view=view,
            ephemeral=True,
        )

    async def handle_mark_claimed_selected(
        self,
        interaction: discord.Interaction,
        giveaway_id: str,
        user_ids: list[str],
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self._is_staff(interaction):
            await interaction.followup.send(
                "❌ Only Bot Developer / Bank Manager can use this.",
                ephemeral=True,
            )
            return

        async with finalize_lock(giveaway_id):
            try:
                doc = await self.svc.mark_winners_claimed(
                    giveaway_id=giveaway_id,
                    selected_winner_ids=user_ids,
                    now=datetime.utcnow(),
                )
            except ValueError as exc:
                await interaction.followup.send(f"❌ {exc}", ephemeral=True)
                return

            await self.runtime.edit_winner_announcement(
                bot=interaction.client,
                giveaway_id=giveaway_id,
                guild=interaction.guild,
                winner_user_ids=list(doc.get("winner_user_ids") or []),
            )

        await interaction.followup.send("✅ Winner(s) marked as claimed.", ephemeral=True)

    async def handle_close_giveaway(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self._is_staff(interaction):
            await interaction.followup.send(
                "❌ Only Bot Developer / Bank Manager can close giveaway.",
                ephemeral=True,
            )
            return

        async with finalize_lock(giveaway_id):
            try:
                doc = await self.svc.close_completed(
                    giveaway_id=giveaway_id,
                    moderator_id=str(interaction.user.id),
                    now=datetime.utcnow(),
                )
            except ValueError as exc:
                await interaction.followup.send(f"❌ {exc}", ephemeral=True)
                return

            await self.runtime.edit_winner_announcement(
                bot=interaction.client,
                giveaway_id=giveaway_id,
                guild=interaction.guild,
                winner_user_ids=list(doc.get("winner_user_ids") or []),
            )

        await interaction.followup.send("✅ Giveaway closed.", ephemeral=True)


_handler: GiveawayHandler | None = None


def get_giveaway_handler() -> GiveawayHandler:
    global _handler
    if _handler is None:
        _handler = GiveawayHandler()
    return _handler
