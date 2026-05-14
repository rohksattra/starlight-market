from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import List
from uuid import uuid4

import discord

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.domains.giveaway_domain import Giveaway, GiveawayInsert, giveaway_effective_status
from app.repositories.giveaway_repo import GiveawayRepository
from app.uis.giveaway_embed import giveaway_panel_embed, giveaway_winners_embed
from app.uis.giveaway_view import GiveawayView
from app.uis.giveaway_winner_view import GiveawayWinnerSelectView, GiveawayWinnerView


log = logging.getLogger("services.giveaway_service")

_finalize_locks: dict[str, asyncio.Lock] = {}


def _finalize_lock(giveaway_id: str) -> asyncio.Lock:
    if giveaway_id not in _finalize_locks:
        _finalize_locks[giveaway_id] = asyncio.Lock()
    return _finalize_locks[giveaway_id]


_service: GiveawayService | None = None


def get_giveaway_service() -> GiveawayService:
    global _service
    if _service is None:
        _service = GiveawayService()
    return _service


class GiveawayService:
    def __init__(self) -> None:
        self.repo = GiveawayRepository()

    def _new_giveaway_id(self) -> str:
        return uuid4().hex

    def _ensure_reroll_allowed(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        return has_any_role(interaction.user, ORDER_MANAGEMENT_ROLES)

    def _winner_mentions(self, winner_user_ids: List[str]) -> str | None:
        mentions = [f"<@{uid}>" for uid in winner_user_ids]
        return " ".join(mentions) if mentions else None

    async def register_persistent_views(self, bot: discord.Client) -> int:
        rows = await self.repo.find_open_or_ended()
        n = 0
        for row in rows:
            gid = row.get("giveaway_id")
            if not gid:
                continue

            doc = await self.repo.get_by_id(str(gid))
            if not doc:
                continue

            join_off = giveaway_effective_status(doc) != "open"
            bot.add_view(GiveawayView(str(gid), join_disabled=join_off))
            n += 1

            if giveaway_effective_status(doc) == "completed" and doc.get("announcement_message_id"):
                bot.add_view(GiveawayWinnerView(str(gid)))
                n += 1

        log.info("Registered %s persistent giveaway view(s)", n)
        return n

    async def recover_stale_giveaways(self, bot: discord.Client) -> None:
        now = datetime.utcnow()
        overdue = await self.repo.find_open_past_end(now=now)
        for doc in overdue:
            gid = str(doc["giveaway_id"])
            asyncio.create_task(self.finalize_giveaway(bot, gid))

        open_docs = await self.repo.find_open_future(now=now, limit=200)
        scheduled: set[str] = set()
        for row in open_docs:
            gid = row["giveaway_id"]
            ends_at = row["ends_at"]
            if gid in scheduled:
                continue
            scheduled.add(gid)
            delay = (ends_at - now).total_seconds()
            if delay > 0:
                asyncio.create_task(self._sleep_then_finalize(bot, gid, delay))

    async def _sleep_then_finalize(self, bot: discord.Client, giveaway_id: str, delay: float) -> None:
        try:
            await asyncio.sleep(max(0.0, delay))
            await self.finalize_giveaway(bot, giveaway_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Scheduled giveaway finalize failed | id=%s", giveaway_id)

    async def create_giveaway(
        self,
        bot: discord.Client,
        *,
        guild: discord.Guild,
        channel: discord.TextChannel,
        host: discord.Member,
        winner_count: int,
        hours: int,
        prize_description: str,
    ) -> str | None:
        giveaway_id = self._new_giveaway_id()
        now = datetime.utcnow()
        ends_at = now + timedelta(hours=float(hours))

        doc: GiveawayInsert = {
            "giveaway_id": giveaway_id,
            "guild_id": guild.id,
            "channel_id": channel.id,
            "host_user_id": str(host.id),
            "winner_count": winner_count,
            "prize_description": prize_description,
            "status": "open",
            "ends_at": ends_at,
        }
        await self.repo.insert_one(doc)

        view = GiveawayView(giveaway_id, join_disabled=False)
        embed = giveaway_panel_embed(doc=doc, guild=guild)
        role = guild.get_role(settings.GIVEAWAY_ROLE_ID)
        ping = f"{role.mention} " if role else None

        try:
            msg = await channel.send(
                content=ping,
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions(roles=True, users=True),
            )
        except discord.HTTPException:
            log.exception("Failed to post giveaway | id=%s", giveaway_id)
            await self.repo.set_status(giveaway_id=giveaway_id, status="cancelled")
            return None

        await self.repo.update_message_id(
            giveaway_id=giveaway_id,
            channel_id=channel.id,
            message_id=msg.id,
        )

        bot.add_view(view)

        delay = (ends_at - datetime.utcnow()).total_seconds()
        if delay > 0:
            asyncio.create_task(self._sleep_then_finalize(bot, giveaway_id, delay))

        return giveaway_id

    async def handle_join(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Use this in the server.", ephemeral=True)
            return
        if interaction.user.bot:
            await interaction.response.send_message("❌ Bots cannot join.", ephemeral=True)
            return

        now = datetime.utcnow()
        doc = await self.repo.get_by_id(giveaway_id)
        if not doc:
            await interaction.response.send_message("❌ Giveaway not found.", ephemeral=True)
            return
        host_id = str(doc.get("host_user_id", ""))
        if host_id == str(interaction.user.id):
            await interaction.response.send_message("❌ You cannot join your own giveaway.", ephemeral=True)
            return
        if giveaway_effective_status(doc) != "open":
            await interaction.response.send_message("❌ This giveaway is no longer accepting entries.", ephemeral=True)
            return
        if doc.get("ends_at") and doc["ends_at"] <= now:
            await interaction.response.send_message("❌ This giveaway has ended.", ephemeral=True)
            return

        added = await self.repo.add_participant(
            giveaway_id=giveaway_id,
            user_id=str(interaction.user.id),
            now=now,
        )
        if added:
            await interaction.response.send_message("✅ You have joined the giveaway.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ You are already entered.", ephemeral=True)

    async def handle_participants(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        doc = await self.repo.get_by_id(giveaway_id)
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
                m = guild.get_member(int(uid))
                if m:
                    name = m.display_name
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

        bot = interaction.client
        doc = await self.repo.get_by_id(giveaway_id)
        if not doc:
            await interaction.followup.send("❌ Giveaway not found.", ephemeral=True)
            return

        await self.finalize_giveaway(bot, giveaway_id)

        doc2 = await self.repo.get_by_id(giveaway_id)
        if not doc2:
            await interaction.followup.send("❌ Giveaway not found.", ephemeral=True)
            return

        ch = bot.get_channel(int(doc2["channel_id"]))
        if not isinstance(ch, discord.TextChannel):
            await interaction.followup.send("❌ Giveaway channel unavailable.", ephemeral=True)
            return

        mid2 = doc2.get("message_id")
        if mid2 is None:
            await interaction.followup.send("❌ Could not load the giveaway message.", ephemeral=True)
            return

        msg = await self._safe_fetch_message(ch, int(mid2))
        if msg is None:
            await interaction.followup.send("❌ Could not load the giveaway message.", ephemeral=True)
            return

        guild = interaction.guild
        view = GiveawayView(giveaway_id, join_disabled=giveaway_effective_status(doc2) != "open")
        try:
            await msg.edit(embed=giveaway_panel_embed(doc=doc2, guild=guild), view=view)
        except discord.HTTPException:
            log.warning("Giveaway refresh edit failed | id=%s", giveaway_id)

        await interaction.followup.send("✅ Giveaway panel updated.", ephemeral=True)

    async def handle_reroll_all(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self._ensure_reroll_allowed(interaction):
            await interaction.followup.send("❌ Only Bot Developer / Bank Manager can reroll.", ephemeral=True)
            return

        async with _finalize_lock(giveaway_id):
            doc = await self.repo.get_by_id(giveaway_id)
            if not doc:
                await interaction.followup.send("❌ Giveaway not found.", ephemeral=True)
                return

            if giveaway_effective_status(doc) != "completed":
                await interaction.followup.send("❌ Only completed giveaways can be rerolled.", ephemeral=True)
                return

            pids: List[str] = list(doc.get("participant_user_ids") or [])
            if not pids:
                await interaction.followup.send("❌ No participants available for reroll.", ephemeral=True)
                return

            k = min(int(doc.get("winner_count", 1)), len(pids))
            winners = random.sample(pids, k=k)

            ok = await self.repo.update_winners(
                giveaway_id=giveaway_id,
                winner_user_ids=winners,
                moderator_id=str(interaction.user.id),
                now=datetime.utcnow(),
            )
            if not ok:
                await interaction.followup.send("❌ Failed to update winners.", ephemeral=True)
                return

            await self._edit_winner_announcement(
                bot=interaction.client,
                giveaway_id=giveaway_id,
                guild=interaction.guild,
                winner_user_ids=winners,
            )

        await interaction.followup.send("✅ All winners rerolled.", ephemeral=True)

    async def handle_reroll_partial_prompt(self, interaction: discord.Interaction, giveaway_id: str) -> None:
        if not self._ensure_reroll_allowed(interaction):
            await interaction.response.send_message("❌ Only Bot Developer / Bank Manager can reroll.", ephemeral=True)
            return

        doc = await self.repo.get_by_id(giveaway_id)
        if not doc:
            await interaction.response.send_message("❌ Giveaway not found.", ephemeral=True)
            return

        if giveaway_effective_status(doc) != "completed":
            await interaction.response.send_message("❌ Only completed giveaways can be rerolled.", ephemeral=True)
            return

        winners: List[str] = list(doc.get("winner_user_ids") or [])
        if not winners:
            await interaction.response.send_message("❌ No winners available to reroll.", ephemeral=True)
            return

        view = GiveawayWinnerSelectView(giveaway_id, winners[:25], interaction.guild)
        await interaction.response.send_message(
            "Choose winner(s) you want to reroll.",
            view=view,
            ephemeral=True,
        )

    async def handle_reroll_partial_selected(
        self,
        interaction: discord.Interaction,
        giveaway_id: str,
        selected_winner_ids: List[str],
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self._ensure_reroll_allowed(interaction):
            await interaction.followup.send("❌ Only Bot Developer / Bank Manager can reroll.", ephemeral=True)
            return

        async with _finalize_lock(giveaway_id):
            doc = await self.repo.get_by_id(giveaway_id)
            if not doc:
                await interaction.followup.send("❌ Giveaway not found.", ephemeral=True)
                return

            if giveaway_effective_status(doc) != "completed":
                await interaction.followup.send("❌ Only completed giveaways can be rerolled.", ephemeral=True)
                return

            participants: List[str] = list(doc.get("participant_user_ids") or [])
            current_winners: List[str] = list(doc.get("winner_user_ids") or [])

            selected = [uid for uid in selected_winner_ids if uid in current_winners]
            if not selected:
                await interaction.followup.send("❌ Selected winner is no longer valid.", ephemeral=True)
                return

            eligible = [
                uid for uid in participants
                if uid not in current_winners
            ]

            if len(eligible) < len(selected):
                await interaction.followup.send(
                    "❌ Not enough eligible participants to replace selected winner(s).",
                    ephemeral=True,
                )
                return

            replacements = random.sample(eligible, k=len(selected))
            replacement_map = dict(zip(selected, replacements))

            new_winners = [
                replacement_map.get(uid, uid)
                for uid in current_winners
            ]

            ok = await self.repo.update_winners(
                giveaway_id=giveaway_id,
                winner_user_ids=new_winners,
                moderator_id=str(interaction.user.id),
                now=datetime.utcnow(),
            )
            if not ok:
                await interaction.followup.send("❌ Failed to update winners.", ephemeral=True)
                return

            await self._edit_winner_announcement(
                bot=interaction.client,
                giveaway_id=giveaway_id,
                guild=interaction.guild,
                winner_user_ids=new_winners,
            )

        await interaction.followup.send("✅ Selected winner(s) rerolled.", ephemeral=True)

    async def _edit_winner_announcement(
        self,
        *,
        bot: discord.Client,
        giveaway_id: str,
        guild: discord.Guild | None,
        winner_user_ids: List[str],
    ) -> None:
        doc = await self.repo.get_by_id(giveaway_id)
        if not doc:
            return

        ch_id = doc.get("announcement_channel_id") or doc.get("channel_id")
        msg_id = doc.get("announcement_message_id")
        if not ch_id or not msg_id:
            return

        ch = bot.get_channel(int(ch_id))
        if not isinstance(ch, discord.TextChannel):
            return

        msg = await self._safe_fetch_message(ch, int(msg_id))
        if msg is None:
            return

        try:
            await msg.edit(
                content=self._winner_mentions(winner_user_ids),
                embed=giveaway_winners_embed(
                    doc=doc,
                    guild=guild,
                    winner_user_ids=winner_user_ids,
                ),
                view=GiveawayWinnerView(giveaway_id),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException:
            log.warning("Giveaway winner announcement edit failed | id=%s", giveaway_id)

    async def _safe_fetch_message(self, channel: discord.TextChannel, message_id: int) -> discord.Message | None:
        try:
            return await channel.fetch_message(message_id)
        except discord.NotFound:
            return None
        except discord.HTTPException:
            return None

    async def finalize_giveaway(self, bot: discord.Client, giveaway_id: str) -> None:
        async with _finalize_lock(giveaway_id):
            await self._finalize_giveaway_locked(bot, giveaway_id)

    async def _finalize_giveaway_locked(self, bot: discord.Client, giveaway_id: str) -> None:
        now = datetime.utcnow()
        doc = await self.repo.get_by_id(giveaway_id)
        if not doc:
            return
        if giveaway_effective_status(doc) == "completed":
            return

        if giveaway_effective_status(doc) == "open":
            ends_at = doc.get("ends_at")
            if isinstance(ends_at, datetime) and ends_at > now:
                return
            await self.repo.lock_if_past_end(giveaway_id=giveaway_id, now=now)

        doc = await self.repo.get_by_id(giveaway_id)
        if not doc or giveaway_effective_status(doc) == "completed":
            return
        if giveaway_effective_status(doc) != "ended":
            return

        pids: List[str] = list(doc.get("participant_user_ids") or [])
        k = min(int(doc.get("winner_count", 1)), len(pids))
        if k > 0:
            winners = random.sample(pids, k=k)
        else:
            winners = []

        guild = bot.get_guild(int(doc.get("guild_id", settings.GUILD_ID)))
        channel = bot.get_channel(int(doc["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            log.error("Giveaway finalize: bad channel | id=%s", giveaway_id)
            return

        mid = doc.get("message_id")
        if mid is None:
            msg = None
        else:
            msg = await self._safe_fetch_message(channel, int(mid))

        view = GiveawayView(giveaway_id, join_disabled=True)
        if msg:
            try:
                completed_doc: Giveaway = {**doc, "status": "completed"}
                await msg.edit(embed=giveaway_panel_embed(doc=completed_doc, guild=guild), view=view)
            except discord.HTTPException:
                log.warning("Giveaway finalize: main message edit failed | id=%s", giveaway_id)

        win_embed = giveaway_winners_embed(doc=doc, guild=guild, winner_user_ids=winners)
        announce: discord.Message | None = None
        try:
            announce = await channel.send(
                content=self._winner_mentions(winners),
                embed=win_embed,
                view=GiveawayWinnerView(giveaway_id),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException:
            log.exception("Giveaway finalize: announcement failed | id=%s", giveaway_id)

        ann_id = announce.id if announce else 0
        ann_ch = announce.channel.id if announce else channel.id

        ok = await self.repo.complete_from_ended(
            giveaway_id=giveaway_id,
            winner_user_ids=winners,
            announcement_channel_id=ann_ch,
            announcement_message_id=ann_id if ann_id else None,
        )
        if not ok:
            if announce:
                try:
                    await announce.delete()
                except discord.HTTPException:
                    pass
            return

        bot.add_view(GiveawayWinnerView(giveaway_id))