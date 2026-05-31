from __future__ import annotations

from datetime import datetime
from typing import List

import discord

from core.config import settings
from app.domains.giveaway_domain import Giveaway, giveaway_effective_status
from app.uis.embed_footer import set_starlight_footer


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

    host_mention = f"- <@{host_id}>" if host_id.isdigit() else "—"
    if guild and host_id.isdigit():
        m = guild.get_member(int(host_id))
        if m:
            host_mention = m.mention

    if status == "open":
        status_line = "🟢 **Open** — use **Join** to enter."
    elif status == "ended":
        status_line = "🔒 **Closed** — drawing winners…"
    elif status == "completed":
        status_line = "✅ **Completed** — winners announced below."
    elif status == "closed":
        status_line = "🔒 **Closed** — all rewards collected."
    elif status == "cancelled":
        status_line = "⛔ **Cancelled**."
    else:
        status_line = "—"

    embed = discord.Embed(
        title="🎁 Giveaway",
        description=prize or "—",
        color=0xFFD700,
    )
    embed.add_field(name="Host", value=host_mention, inline=True)
    embed.add_field(name="Winners", value=f"**{winner_count}**", inline=True)
    embed.add_field(name="Participants", value=f"**{participant_count}**", inline=True)
    embed.add_field(name="Ends", value=discord.utils.format_dt(ends_at, style="F"), inline=False)
    embed.add_field(name="Status", value=status_line, inline=False)
    set_starlight_footer(embed)
    return embed


def giveaway_winners_embed(
    *,
    doc: Giveaway,
    guild: discord.Guild | None,
    winner_user_ids: List[str],
) -> discord.Embed:
    prize = str(doc.get("prize_description", ""))[:4096]
    host_id = str(doc.get("host_user_id", ""))

    host_mention = f"- <@{host_id}>" if host_id.isdigit() else "—"
    if guild and host_id.isdigit():
        m = guild.get_member(int(host_id))
        if m:
            host_mention = m.mention

    claimed_ids = set(str(uid) for uid in doc.get("claimed_winner_user_ids") or [])

    if winner_user_ids:
        lines = []
        for i, uid in enumerate(winner_user_ids, start=1):
            mention = f"<@{uid}>"
            if guild:
                mem = guild.get_member(int(uid))
                if mem:
                    mention = mem.mention

            claimed_mark = " ✅" if str(uid) in claimed_ids else ""
            lines.append(f"**{i}.** {mention}{claimed_mark}")

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

    status = giveaway_effective_status(doc)
    if status == "closed":
        embed.add_field(
            name="Status",
            value="🔒 Giveaway closed. All rewards have been collected.",
            inline=False,
        )
    elif status == "cancelled":
        embed.add_field(
            name="Status",
            value="⛔ Giveaway cancelled.",
            inline=False,
        )

    reroll_count = int(doc.get("reroll_count", 0) or 0)
    last_rerolled_by = str(doc.get("last_rerolled_by", "") or "")
    last_rerolled_at = doc.get("last_rerolled_at")

    if reroll_count > 0:
        reroll_line = f"🔄 Rerolled **{reroll_count}** time(s)."
        if last_rerolled_by.isdigit():
            reroll_line += f"\nLast rerolled by <@{last_rerolled_by}>."
        if isinstance(last_rerolled_at, datetime):
            reroll_line += f"\nAt {discord.utils.format_dt(last_rerolled_at, style='F')}."

        embed.add_field(name="Reroll Info", value=reroll_line, inline=False)

    if status not in ("closed", "cancelled"):
        bank_manager_mention = f"<@&{settings.BANK_MANAGER_ROLE_ID}>"
        embed.add_field(
            name="Reward",
            value=f"Please ping {bank_manager_mention} to collect your reward.",
            inline=False,
        )

    set_starlight_footer(embed)
    return embed