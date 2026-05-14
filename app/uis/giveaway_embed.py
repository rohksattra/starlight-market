from __future__ import annotations

from datetime import datetime
from typing import List

import discord

from app.domains.giveaway_domain import Giveaway, giveaway_effective_status


def giveaway_panel_embed(*, doc: Giveaway, guild: discord.Guild | None) -> discord.Embed:
    host_id = doc.get("host_user_id", "")
    prize = str(doc.get("prize_description", ""))[:4096]
    winner_count = int(doc.get("winner_count", 1))
    ends_at = doc.get("ends_at")
    if not isinstance(ends_at, datetime):
        ends_at = datetime.utcnow()
    status = giveaway_effective_status(doc)
    pids: List[str] = list(doc.get("participant_user_ids") or [])
    participant_count = len(pids)

    host_mention = f"<@{host_id}>" if host_id.isdigit() else "—"
    if guild and host_id.isdigit():
        m = guild.get_member(int(host_id))
        if m:
            host_mention = m.mention

    if status == "open":
        status_line = "🟢 **Open** — use **Join** to enter."
    elif status == "ended":
        status_line = "🔒 **Closed** — drawing winners…"
    elif status == "cancelled":
        status_line = "⛔ **Cancelled**."
    else:
        status_line = "✅ **Completed** — winners announced below."

    embed = discord.Embed(
        title="🎁 Giveaway",
        description=prize or "—",
        color=0xE91E63,
    )
    embed.add_field(name="Host", value=host_mention, inline=True)
    embed.add_field(name="Winners", value=f"**{winner_count}**", inline=True)
    embed.add_field(name="Participants", value=f"**{participant_count}**", inline=True)
    embed.add_field(name="Ends", value=discord.utils.format_dt(ends_at, style="F"), inline=False)
    embed.add_field(name="Status", value=status_line, inline=False)
    embed.set_footer(text="🌟 Starlight Market")
    return embed


def giveaway_winners_embed(
    *,
    doc: Giveaway,
    guild: discord.Guild | None,
    winner_user_ids: List[str],
) -> discord.Embed:
    prize = str(doc.get("prize_description", ""))[:4096]
    host_id = str(doc.get("host_user_id", ""))
    host_mention = f"<@{host_id}>" if host_id.isdigit() else "—"
    if guild and host_id.isdigit():
        m = guild.get_member(int(host_id))
        if m:
            host_mention = m.mention

    if winner_user_ids:
        lines = []
        for i, uid in enumerate(winner_user_ids, start=1):
            mention = f"<@{uid}>"
            if guild:
                mem = guild.get_member(int(uid))
                if mem:
                    mention = mem.mention
            lines.append(f"**{i}.** {mention}")
        winners_block = "\n".join(lines)
    else:
        winners_block = "*No entries — no winners.*"

    embed = discord.Embed(
        title="🎁 Giveaway Winners",
        description=prize or "—",
        color=0xFFD700,
    )
    embed.add_field(name="Host", value=host_mention, inline=True)
    embed.add_field(name="Winners", value=winners_block, inline=False)
    embed.set_footer(text="🌟 Starlight Market")
    return embed
