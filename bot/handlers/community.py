"""Giveaway Discord runtime (create, recover, finalize)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List

import discord
from discord.ext import commands

from bot.handlers.community_actions import GiveawayActionsMixin
from bot.ui.community import (
    GiveawayView,
    GiveawayWinnerView,
    giveaway_panel_embed,
    giveaway_winners_embed,
)
from core.tenant import GameContext, all_contexts, get_context
from core.time import utc_now
from models.enums import ORDER_MANAGEMENT_ROLES
from models.giveaway import Giveaway, GiveawayInsert, giveaway_effective_status
from services.giveaways import GiveawayService, finalize_lock
from utils.permissions import has_any_role

log = logging.getLogger("bot.handlers.community")


async def _safe_fetch_message(channel: discord.TextChannel, message_id: int) -> discord.Message | None:
    try:
        return await channel.fetch_message(message_id)
    except (discord.NotFound, discord.HTTPException):
        return None


class CommunityHandler(GiveawayActionsMixin):
    def _resolve_ctx(self, guild: discord.Guild | None) -> GameContext | None:
        if guild is None:
            return None
        return get_context(guild.id)

    def _svc(self, ctx: GameContext) -> GiveawayService:
        return GiveawayService(ctx)

    def _svc_for_guild(self, guild: discord.Guild | None) -> GiveawayService | None:
        ctx = self._resolve_ctx(guild)
        if ctx is None:
            return None
        return self._svc(ctx)

    def _svc_for_guild_id(self, guild_id: int) -> GiveawayService | None:
        ctx = get_context(guild_id)
        if ctx is None:
            return None
        return self._svc(ctx)

    def _is_staff(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        ctx = get_context(interaction.guild.id)
        if ctx is None:
            return False
        return has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES)

    def winner_mentions(self, winner_user_ids: List[str]) -> str | None:
        mentions = [f"<@{uid}>" for uid in winner_user_ids]
        return " ".join(mentions) if mentions else None

    def main_view_for_status(self, giveaway_id: str, status: str) -> GiveawayView:
        is_open = status == "open"
        return GiveawayView(
            giveaway_id,
            join_disabled=not is_open,
            refresh_disabled=not is_open,
            cancel_disabled=not is_open,
        )

    def winner_view_for_status(self, giveaway_id: str, status: str) -> GiveawayWinnerView:
        return GiveawayWinnerView(
            giveaway_id,
            disabled=status in ("closed", "cancelled"),
        )

    async def register_persistent_views(self, bot: commands.Bot) -> int:
        n = 0
        for ctx in all_contexts():
            svc = self._svc(ctx)
            rows = await svc.find_open_or_ended()
            for row in rows:
                gid = row.get("giveaway_id")
                if not gid:
                    continue
                doc = await svc.get_by_id(str(gid))
                if not doc:
                    continue
                status = giveaway_effective_status(doc)
                bot.add_view(self.main_view_for_status(str(gid), status))
                n += 1
                if status in ("completed", "closed") and doc.get("announcement_message_id"):
                    bot.add_view(self.winner_view_for_status(str(gid), status))
                    n += 1
        log.info("Registered %s persistent giveaway view(s)", n)
        return n

    async def recover_stale_giveaways(self, bot: commands.Bot) -> None:
        for ctx in all_contexts():
            svc = self._svc(ctx)
            now = utc_now()
            overdue = await svc.find_open_past_end(now=now)
            for doc in overdue:
                gid = str(doc["giveaway_id"])
                asyncio.create_task(self.finalize_giveaway(bot, gid, ctx))

            open_docs = await svc.find_open_future(now=now, limit=200)
            scheduled: set[str] = set()
            for row in open_docs:
                gid = row["giveaway_id"]
                ends_at = row["ends_at"]
                if gid in scheduled:
                    continue
                scheduled.add(gid)
                delay = (ends_at - now).total_seconds()
                if delay > 0:
                    asyncio.create_task(self._sleep_then_finalize(bot, gid, delay, ctx))

    async def _sleep_then_finalize(
        self,
        bot: discord.Client,
        giveaway_id: str,
        delay: float,
        ctx: GameContext,
    ) -> None:
        try:
            await asyncio.sleep(max(0.0, delay))
            await self.finalize_giveaway(bot, giveaway_id, ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Scheduled giveaway finalize failed | id=%s game=%s", giveaway_id, ctx.game)

    async def create_giveaway(
        self,
        bot: discord.Client,
        *,
        ctx: GameContext,
        guild: discord.Guild,
        channel: discord.TextChannel,
        host: discord.Member,
        winner_count: int,
        hours: int,
        prize_description: str,
    ) -> str | None:
        svc = self._svc(ctx)
        giveaway_id = svc.new_giveaway_id()
        now = utc_now()
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
        await svc.insert_giveaway(doc)

        view = self.main_view_for_status(giveaway_id, "open")
        role = guild.get_role(ctx.roles.giveaway)
        ping = f"{role.mention} " if role else None

        try:
            msg = await channel.send(
                content=ping,
                embed=giveaway_panel_embed(doc=doc, guild=guild),
                view=view,
                allowed_mentions=discord.AllowedMentions(roles=True, users=True),
            )
        except discord.HTTPException:
            log.exception("Failed to post giveaway | id=%s", giveaway_id)
            await svc.set_status(giveaway_id=giveaway_id, status="cancelled")
            return None

        await svc.update_message_id(
            giveaway_id=giveaway_id,
            channel_id=channel.id,
            message_id=msg.id,
        )
        bot.add_view(view)

        delay = (ends_at - utc_now()).total_seconds()
        if delay > 0:
            asyncio.create_task(self._sleep_then_finalize(bot, giveaway_id, delay, ctx))

        return giveaway_id

    async def edit_main_panel(
        self,
        *,
        bot: discord.Client,
        giveaway_id: str,
        guild: discord.Guild | None,
        doc: Giveaway,
    ) -> None:
        status = giveaway_effective_status(doc)
        channel = bot.get_channel(int(doc["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return
        message_id = doc.get("message_id")
        if message_id is None:
            return
        msg = await _safe_fetch_message(channel, int(message_id))
        if msg is None:
            return
        try:
            await msg.edit(
                embed=giveaway_panel_embed(doc=doc, guild=guild),
                view=self.main_view_for_status(giveaway_id, status),
            )
        except discord.HTTPException:
            log.warning("Giveaway main panel edit failed | id=%s", giveaway_id)

    async def edit_winner_announcement(
        self,
        *,
        bot: discord.Client,
        giveaway_id: str,
        guild: discord.Guild | None,
        winner_user_ids: List[str],
        ctx: GameContext | None = None,
    ) -> None:
        resolved_ctx = ctx or self._resolve_ctx(guild)
        if resolved_ctx is None and guild is not None:
            resolved_ctx = get_context(guild.id)
        svc = self._svc(resolved_ctx) if resolved_ctx else None
        if svc is None:
            return

        doc = await svc.get_by_id(giveaway_id)
        if not doc:
            return

        status = giveaway_effective_status(doc)
        ch_id = doc.get("announcement_channel_id") or doc.get("channel_id")
        msg_id = doc.get("announcement_message_id")
        if not ch_id or not msg_id:
            return

        ch = bot.get_channel(int(ch_id))
        if not isinstance(ch, discord.TextChannel):
            return

        msg = await _safe_fetch_message(ch, int(msg_id))
        if msg is None:
            return

        bank_role_id = resolved_ctx.roles.bank_manager if resolved_ctx else 0
        try:
            await msg.edit(
                content=self.winner_mentions(winner_user_ids),
                embed=giveaway_winners_embed(
                    doc=doc,
                    guild=guild,
                    winner_user_ids=winner_user_ids,
                    bank_manager_role_id=bank_role_id,
                ),
                view=self.winner_view_for_status(giveaway_id, status),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException:
            log.warning("Giveaway winner announcement edit failed | id=%s", giveaway_id)

    async def finalize_giveaway(
        self,
        bot: discord.Client,
        giveaway_id: str,
        ctx: GameContext | None = None,
    ) -> None:
        async with finalize_lock(giveaway_id):
            await self._finalize_giveaway_locked(bot, giveaway_id, ctx)

    async def _finalize_giveaway_locked(
        self,
        bot: discord.Client,
        giveaway_id: str,
        ctx: GameContext | None,
    ) -> None:
        now = utc_now()

        svc: GiveawayService | None = None
        if ctx is not None:
            svc = self._svc(ctx)
        else:
            for tenant in all_contexts():
                candidate = self._svc(tenant)
                doc_probe = await candidate.get_by_id(giveaway_id)
                if doc_probe:
                    svc = candidate
                    ctx = tenant
                    break

        if svc is None or ctx is None:
            return

        doc = await svc.get_by_id(giveaway_id)
        if not doc:
            return

        status = giveaway_effective_status(doc)
        if status in ("completed", "closed", "cancelled"):
            return

        if status == "open":
            ends_at = doc.get("ends_at")
            if isinstance(ends_at, datetime) and ends_at > now:
                return
            await svc.lock_if_past_end(giveaway_id=giveaway_id, now=now)

        doc = await svc.get_by_id(giveaway_id)
        if not doc or giveaway_effective_status(doc) != "ended":
            return

        winners = await svc.resolve_pending_winners(giveaway_id=giveaway_id, doc=doc)

        guild = bot.get_guild(int(doc.get("guild_id", ctx.guild_id)))
        channel = bot.get_channel(int(doc["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            log.error("Giveaway finalize: bad channel | id=%s", giveaway_id)
            return

        await self.edit_main_panel(
            bot=bot,
            giveaway_id=giveaway_id,
            guild=guild,
            doc={**doc, "status": "ended"},
        )

        try:
            announce = await channel.send(
                content=self.winner_mentions(winners),
                embed=giveaway_winners_embed(
                    doc=doc,
                    guild=guild,
                    winner_user_ids=winners,
                    bank_manager_role_id=ctx.roles.bank_manager,
                ),
                view=self.winner_view_for_status(giveaway_id, "completed"),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException:
            log.exception("Giveaway winner announcement post failed | id=%s", giveaway_id)
            return

        ok = await svc.complete_from_ended(
            giveaway_id=giveaway_id,
            winner_user_ids=winners,
            announcement_channel_id=announce.channel.id,
            announcement_message_id=announce.id,
        )
        if not ok:
            try:
                await announce.delete()
            except discord.HTTPException:
                pass
            return

        doc = await svc.get_by_id(giveaway_id)
        if doc:
            await self.edit_main_panel(
                bot=bot,
                giveaway_id=giveaway_id,
                guild=guild,
                doc=doc,
            )

        bot.add_view(self.winner_view_for_status(giveaway_id, "completed"))


_handler: CommunityHandler | None = None


def get_community_handler() -> CommunityHandler:
    global _handler
    if _handler is None:
        _handler = CommunityHandler()
    return _handler
