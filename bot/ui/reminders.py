"""CoA meteor and world-boost reminder embeds."""
from __future__ import annotations

from datetime import datetime, timezone

import discord

from bot.ui.shared import set_starlight_footer
from core.tenant import GameContext
from services.coa_reminders import CoAWorld, METEOR_DURATION_MINUTES, format_boost_remaining

EMBED_COLOR = 0xFFD700


def _aware(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when


def _dt(when: datetime, style: str) -> str:
    return discord.utils.format_dt(_aware(when), style=style)


def meteor_reminder_embed(
    *,
    event_start: datetime,
    event_end: datetime,
    ctx: GameContext | None = None,
) -> discord.Embed:
    start = _dt(event_start, "t")
    end = _dt(event_end, "t")
    embed = discord.Embed(
        title="☄️ Meteor Incoming",
        description=(
            f"A meteor is dropping in **{_dt(event_start, 'R')}**.\n\n"
            f"**Event Time:** **{start}**\n"
            f"**Duration:** **{METEOR_DURATION_MINUTES} minutes ({start} – {end})**\n\n"
            "Get ready and head to the crash site."
        ),
        color=EMBED_COLOR,
    )
    return set_starlight_footer(embed, ctx=ctx, detail="Meteor Reminder", include_button_notice=False)


def world_boost_embed(
    *,
    world: CoAWorld,
    ends_at: datetime | None,
    ctx: GameContext | None = None,
) -> discord.Embed:
    remaining = format_boost_remaining(world.boost_remaining)
    ending = ""
    if remaining:
        ending = f" **Time left:** **{remaining}**."
        if ends_at is not None:
            ending += f" It ends **{_dt(ends_at, 'R')}**."
    elif ends_at is not None:
        ending = f" It ends **{_dt(ends_at, 'R')}**."
    embed = discord.Embed(
        title="🚀 World Boost Active",
        description=(
            f"A player just boosted **{world.name}**. Everyone there gets "
            f"**+50% EXP** for the rest of the boost.{ending}\n\n"
            "Log in and start grinding."
        ),
        color=EMBED_COLOR,
    )
    return set_starlight_footer(
        embed, ctx=ctx, detail="World Boost Reminder", include_button_notice=False
    )
