from __future__ import annotations

import logging
from typing import List

import discord

from app.domains.giveaway_domain import Giveaway
from app.views.giveaway_embed import giveaway_panel_embed, giveaway_winners_embed


log = logging.getLogger("discord.giveaway_presenter")


async def safe_fetch_message(channel: discord.TextChannel, message_id: int) -> discord.Message | None:
    try:
        return await channel.fetch_message(message_id)
    except discord.NotFound:
        return None
    except discord.HTTPException:
        return None


async def post_giveaway_panel(
    *,
    channel: discord.TextChannel,
    guild: discord.Guild,
    doc: Giveaway,
    view: discord.ui.View,
    role_ping: str | None,
) -> discord.Message | None:
    try:
        return await channel.send(
            content=role_ping,
            embed=giveaway_panel_embed(doc=doc, guild=guild),
            view=view,
            allowed_mentions=discord.AllowedMentions(roles=True, users=True),
        )
    except discord.HTTPException:
        log.exception("Failed to post giveaway | id=%s", doc.get("giveaway_id"))
        return None


async def post_winner_announcement(
    *,
    channel: discord.TextChannel,
    guild: discord.Guild | None,
    doc: Giveaway,
    winner_user_ids: List[str],
    view: discord.ui.View,
    winner_mentions: str | None,
) -> discord.Message | None:
    try:
        return await channel.send(
            content=winner_mentions,
            embed=giveaway_winners_embed(
                doc=doc,
                guild=guild,
                winner_user_ids=winner_user_ids,
            ),
            view=view,
            allowed_mentions=discord.AllowedMentions(users=True),
        )
    except discord.HTTPException:
        log.exception("Giveaway winner announcement post failed | id=%s", doc.get("giveaway_id"))
        return None


async def edit_main_panel(
    *,
    bot: discord.Client,
    giveaway_id: str,
    guild: discord.Guild | None,
    doc: Giveaway,
    view: discord.ui.View,
) -> None:
    channel = bot.get_channel(int(doc["channel_id"]))
    if not isinstance(channel, discord.TextChannel):
        return

    message_id = doc.get("message_id")
    if message_id is None:
        return

    msg = await safe_fetch_message(channel, int(message_id))
    if msg is None:
        return

    try:
        await msg.edit(
            embed=giveaway_panel_embed(doc=doc, guild=guild),
            view=view,
        )
    except discord.HTTPException:
        log.warning("Giveaway main panel edit failed | id=%s", giveaway_id)


async def edit_winner_announcement(
    *,
    bot: discord.Client,
    giveaway_id: str,
    guild: discord.Guild | None,
    doc: Giveaway,
    winner_user_ids: List[str],
    view: discord.ui.View,
    winner_mentions: str | None,
) -> None:
    ch_id = doc.get("announcement_channel_id") or doc.get("channel_id")
    msg_id = doc.get("announcement_message_id")
    if not ch_id or not msg_id:
        return

    ch = bot.get_channel(int(ch_id))
    if not isinstance(ch, discord.TextChannel):
        return

    msg = await safe_fetch_message(ch, int(msg_id))
    if msg is None:
        return

    try:
        await msg.edit(
            content=winner_mentions,
            embed=giveaway_winners_embed(
                doc=doc,
                guild=guild,
                winner_user_ids=winner_user_ids,
            ),
            view=view,
            allowed_mentions=discord.AllowedMentions(users=True),
        )
    except discord.HTTPException:
        log.warning("Giveaway winner announcement edit failed | id=%s", giveaway_id)
