"""Giveaway button/select handlers."""
from __future__ import annotations

from typing import List

import discord

from bot.ui.community import GiveawayWinnerSelectView
from core.time import utc_now
from services.giveaways import finalize_lock


class GiveawayActionsMixin:
    async def handle_join(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Use this in the server.", ephemeral=True)
            return

        if interaction.user.bot:
            await interaction.response.send_message("❌ Bots cannot join.", ephemeral=True)
            return

        svc = self._svc_for_guild(interaction.guild)
        if svc is None:
            await interaction.response.send_message("❌ Unknown game server.", ephemeral=True)
            return

        try:
            added = await svc.join(
                giveaway_id=giveaway_id,
                user_id=str(interaction.user.id),
                now=utc_now(),
            )
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        if added:
            await interaction.response.send_message("✅ You have joined the giveaway.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ You are already entered.", ephemeral=True)

    async def handle_participants(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        svc = self._svc_for_guild(interaction.guild)
        if svc is None:
            await interaction.response.send_message("❌ Unknown game server.", ephemeral=True)
            return

        doc = await svc.get_by_id(giveaway_id)
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

        svc = self._svc_for_guild(interaction.guild)
        if svc is None:
            await interaction.followup.send("❌ Unknown game server.", ephemeral=True)
            return

        try:
            await svc.require_open(giveaway_id)
        except ValueError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        bot = interaction.client
        ctx = self._resolve_ctx(interaction.guild)
        await self.finalize_giveaway(bot, giveaway_id, ctx)

        doc = await svc.get_by_id(giveaway_id)
        if not doc:
            await interaction.followup.send("❌ Giveaway not found.", ephemeral=True)
            return

        await self.edit_main_panel(
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

        svc = self._svc_for_guild(interaction.guild)
        if svc is None:
            await interaction.followup.send("❌ Unknown game server.", ephemeral=True)
            return

        async with finalize_lock(giveaway_id):
            try:
                doc = await svc.cancel_open(
                    giveaway_id=giveaway_id,
                    moderator_id=str(interaction.user.id),
                    now=utc_now(),
                )
            except ValueError as exc:
                await interaction.followup.send(f"❌ {exc}", ephemeral=True)
                return

            await self.edit_main_panel(
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

        svc = self._svc_for_guild(interaction.guild)
        if svc is None:
            await interaction.followup.send("❌ Unknown game server.", ephemeral=True)
            return

        async with finalize_lock(giveaway_id):
            try:
                winners = await svc.reroll_all_unclaimed(
                    giveaway_id=giveaway_id,
                    moderator_id=str(interaction.user.id),
                    now=utc_now(),
                )
            except ValueError as exc:
                await interaction.followup.send(f"❌ {exc}", ephemeral=True)
                return

            await self.edit_winner_announcement(
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

        svc = self._svc_for_guild(interaction.guild)
        if svc is None:
            await interaction.response.send_message("❌ Unknown game server.", ephemeral=True)
            return

        try:
            doc = await svc.require_completed(giveaway_id)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        winners = svc.unclaimed_winners(doc)
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

        svc = self._svc_for_guild(interaction.guild)
        if svc is None:
            await interaction.followup.send("❌ Unknown game server.", ephemeral=True)
            return

        async with finalize_lock(giveaway_id):
            try:
                winners = await svc.reroll_selected(
                    giveaway_id=giveaway_id,
                    selected_winner_ids=user_ids,
                    moderator_id=str(interaction.user.id),
                    now=utc_now(),
                )
            except ValueError as exc:
                await interaction.followup.send(f"❌ {exc}", ephemeral=True)
                return

            await self.edit_winner_announcement(
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

        svc = self._svc_for_guild(interaction.guild)
        if svc is None:
            await interaction.response.send_message("❌ Unknown game server.", ephemeral=True)
            return

        try:
            doc = await svc.require_completed(giveaway_id)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        winners = svc.unclaimed_winners(doc)
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

        svc = self._svc_for_guild(interaction.guild)
        if svc is None:
            await interaction.followup.send("❌ Unknown game server.", ephemeral=True)
            return

        async with finalize_lock(giveaway_id):
            try:
                doc = await svc.mark_winners_claimed(
                    giveaway_id=giveaway_id,
                    selected_winner_ids=user_ids,
                    now=utc_now(),
                )
            except ValueError as exc:
                await interaction.followup.send(f"❌ {exc}", ephemeral=True)
                return

            await self.edit_winner_announcement(
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

        svc = self._svc_for_guild(interaction.guild)
        if svc is None:
            await interaction.followup.send("❌ Unknown game server.", ephemeral=True)
            return

        async with finalize_lock(giveaway_id):
            try:
                doc = await svc.close_completed(
                    giveaway_id=giveaway_id,
                    moderator_id=str(interaction.user.id),
                    now=utc_now(),
                )
            except ValueError as exc:
                await interaction.followup.send(f"❌ {exc}", ephemeral=True)
                return

            await self.edit_winner_announcement(
                bot=interaction.client,
                giveaway_id=giveaway_id,
                guild=interaction.guild,
                winner_user_ids=list(doc.get("winner_user_ids") or []),
            )

        await interaction.followup.send("✅ Giveaway closed.", ephemeral=True)
