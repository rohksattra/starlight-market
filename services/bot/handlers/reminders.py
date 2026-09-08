"""CoA-only meteor and world-boost reminder loops."""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from bot.ui.reminders import meteor_reminder_embed, world_boost_embed
from core.tenant import GameContext, all_contexts
from core.time import utc_now
from services.coa_reminders import (
    BOOST_POLL_SECONDS,
    WorldBoostService,
    boost_end_at,
    fetch_worlds,
    meteor_event_window,
    meteor_slot_key,
    next_meteor_reminder_at,
)

log = logging.getLogger("bot.handlers.reminders")
_ROLE_MENTIONS = discord.AllowedMentions(roles=True)


def _text_channel(bot: commands.Bot, guild_id: int, channel_id: int) -> discord.TextChannel | None:
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None
    channel = guild.get_channel(channel_id)
    return channel if isinstance(channel, discord.TextChannel) else None


async def _send_reminder(
    *,
    bot: commands.Bot,
    ctx: GameContext,
    channel_id: int,
    role_id: int,
    embed: discord.Embed,
    kind: str,
) -> None:
    channel = _text_channel(bot, ctx.guild_id, channel_id)
    if channel is None:
        log.warning("Reminder channel missing | kind=%s game=%s", kind, ctx.game)
        return

    guild = channel.guild
    role = guild.get_role(role_id) if role_id else None
    try:
        await channel.send(
            content=role.mention if role else None,
            embed=embed,
            allowed_mentions=_ROLE_MENTIONS,
        )
    except discord.HTTPException:
        log.exception("Failed to send reminder | kind=%s game=%s", kind, ctx.game)


async def _meteor_loop(bot: commands.Bot, ctx: GameContext) -> None:
    await bot.wait_until_ready()
    sent_slots: set[str] = set()
    while not bot.is_closed():
        try:
            now = utc_now()
            when = next_meteor_reminder_at(now, sent_slots=sent_slots)
            delay = (when - now).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            if bot.is_closed():
                return
            slot = meteor_slot_key(when)
            if slot in sent_slots:
                continue
            start, end = meteor_event_window(when)
            await _send_reminder(
                bot=bot,
                ctx=ctx,
                channel_id=ctx.channels.meteor_reminder,
                role_id=ctx.roles.meteor,
                embed=meteor_reminder_embed(event_start=start, event_end=end, ctx=ctx),
                kind="meteor",
            )
            sent_slots.add(slot)
            if len(sent_slots) > 48:
                sent_slots = set(sorted(sent_slots)[-12:])
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Meteor reminder loop failed | game=%s", ctx.game)
            await asyncio.sleep(60)


async def _boost_loop(bot: commands.Bot, ctx: GameContext) -> None:
    await bot.wait_until_ready()
    service = WorldBoostService(ctx.db_name)
    await service.start()
    while not bot.is_closed():
        try:
            worlds = await fetch_worlds()
            now = utc_now()
            for world in await service.consume(worlds, now=now):
                await _send_reminder(
                    bot=bot,
                    ctx=ctx,
                    channel_id=ctx.channels.world_boost,
                    role_id=ctx.roles.world_boost,
                    embed=world_boost_embed(
                        world=world,
                        ends_at=boost_end_at(now, world.boost_remaining),
                        ctx=ctx,
                    ),
                    kind="world_boost",
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("World boost reminder loop failed | game=%s", ctx.game)
        await asyncio.sleep(BOOST_POLL_SECONDS)


async def start_coa_reminders(bot: commands.Bot) -> None:
    started = 0
    for ctx in all_contexts():
        if ctx.game != "coa":
            continue
        if ctx.channels.meteor_reminder:
            asyncio.create_task(_meteor_loop(bot, ctx), name=f"coa-meteor-{ctx.guild_id}")
            started += 1
        if ctx.channels.world_boost:
            asyncio.create_task(_boost_loop(bot, ctx), name=f"coa-boost-{ctx.guild_id}")
            started += 1
    if started:
        log.info("CoA reminder loops started | tasks=%s", started)
