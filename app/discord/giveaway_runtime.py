from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List

import discord

from core.config import settings
from app.domains.giveaway_domain import Giveaway, GiveawayInsert, giveaway_effective_status
from app.discord.giveaway_presenter import (
    edit_main_panel,
    edit_winner_announcement,
    post_giveaway_panel,
    post_winner_announcement,
)
from app.services.giveaway_service import GiveawayService, finalize_lock
from app.views.giveaway_view import GiveawayView
from app.views.giveaway_winner_view import GiveawayWinnerView


log = logging.getLogger("discord.giveaway_runtime")

_runtime: GiveawayRuntime | None = None


def get_giveaway_runtime() -> GiveawayRuntime:
    global _runtime
    if _runtime is None:
        _runtime = GiveawayRuntime()
    return _runtime


class GiveawayRuntime:
    def __init__(self) -> None:
        self.svc = GiveawayService()

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

    async def register_persistent_views(self, bot: discord.Client) -> int:
        rows = await self.svc.find_open_or_ended()
        n = 0

        for row in rows:
            gid = row.get("giveaway_id")
            if not gid:
                continue

            doc = await self.svc.get_by_id(str(gid))
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

    async def recover_stale_giveaways(self, bot: discord.Client) -> None:
        now = datetime.utcnow()
        overdue = await self.svc.find_open_past_end(now=now)
        for doc in overdue:
            gid = str(doc["giveaway_id"])
            asyncio.create_task(self.finalize_giveaway(bot, gid))

        open_docs = await self.svc.find_open_future(now=now, limit=200)
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
        giveaway_id = self.svc.new_giveaway_id()
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
        await self.svc.insert_giveaway(doc)

        view = self.main_view_for_status(giveaway_id, "open")
        role = guild.get_role(settings.GIVEAWAY_ROLE_ID)
        ping = f"{role.mention} " if role else None

        msg = await post_giveaway_panel(
            channel=channel,
            guild=guild,
            doc=doc,
            view=view,
            role_ping=ping,
        )
        if msg is None:
            await self.svc.set_status(giveaway_id=giveaway_id, status="cancelled")
            return None

        await self.svc.update_message_id(
            giveaway_id=giveaway_id,
            channel_id=channel.id,
            message_id=msg.id,
        )

        bot.add_view(view)

        delay = (ends_at - datetime.utcnow()).total_seconds()
        if delay > 0:
            asyncio.create_task(self._sleep_then_finalize(bot, giveaway_id, delay))

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
        await edit_main_panel(
            bot=bot,
            giveaway_id=giveaway_id,
            guild=guild,
            doc=doc,
            view=self.main_view_for_status(giveaway_id, status),
        )

    async def edit_winner_announcement(
        self,
        *,
        bot: discord.Client,
        giveaway_id: str,
        guild: discord.Guild | None,
        winner_user_ids: List[str],
    ) -> None:
        doc = await self.svc.get_by_id(giveaway_id)
        if not doc:
            return

        status = giveaway_effective_status(doc)
        await edit_winner_announcement(
            bot=bot,
            giveaway_id=giveaway_id,
            guild=guild,
            doc=doc,
            winner_user_ids=winner_user_ids,
            view=self.winner_view_for_status(giveaway_id, status),
            winner_mentions=self.winner_mentions(winner_user_ids),
        )

    async def finalize_giveaway(self, bot: discord.Client, giveaway_id: str) -> None:
        async with finalize_lock(giveaway_id):
            await self._finalize_giveaway_locked(bot, giveaway_id)

    async def _finalize_giveaway_locked(self, bot: discord.Client, giveaway_id: str) -> None:
        now = datetime.utcnow()
        doc = await self.svc.get_by_id(giveaway_id)
        if not doc:
            return

        status = giveaway_effective_status(doc)
        if status in ("completed", "closed", "cancelled"):
            return

        if status == "open":
            ends_at = doc.get("ends_at")
            if isinstance(ends_at, datetime) and ends_at > now:
                return

            await self.svc.lock_if_past_end(giveaway_id=giveaway_id, now=now)

        doc = await self.svc.get_by_id(giveaway_id)
        if not doc or giveaway_effective_status(doc) != "ended":
            return

        winners = await self.svc.resolve_pending_winners(giveaway_id=giveaway_id, doc=doc)

        guild = bot.get_guild(int(doc.get("guild_id", settings.GUILD_ID)))
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

        announce = await post_winner_announcement(
            channel=channel,
            guild=guild,
            doc=doc,
            winner_user_ids=winners,
            view=self.winner_view_for_status(giveaway_id, "completed"),
            winner_mentions=self.winner_mentions(winners),
        )
        if announce is None:
            return

        ok = await self.svc.complete_from_ended(
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

        doc = await self.svc.get_by_id(giveaway_id)
        if doc:
            await self.edit_main_panel(
                bot=bot,
                giveaway_id=giveaway_id,
                guild=guild,
                doc=doc,
            )

        bot.add_view(self.winner_view_for_status(giveaway_id, "completed"))
