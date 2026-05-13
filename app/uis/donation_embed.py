from __future__ import annotations

import discord


def fmt(value: int) -> str:
    return f"{value:,}"


def donation_embed(*, donor: discord.Member, gold: int, description: str) -> discord.Embed:
    raw = (description or "").strip()
    detail_line = raw.replace("\n", " ")[:900] if raw else "—"

    tier_block = ""
    if donor_tier_role_id is not None:
        tier_block = (
            f"**Donor tier**\n"
            f"- ***<@&{donor_tier_role_id}>***\n"
        )

    body = (
        f"**Donor**\n"
        f"- ***<@{donor_id}>***\n"
        f"**Gold**\n"
        f"- 🪙 ***{fmt(gold)}***\n"
        f"{tier_block}"
        f"**Detail**\n"
        f"- ***{detail_line}***\n\n"
        "*Thank you for your donation.*"
    )

    embed = discord.Embed(
        title="🎁 New Donation",
        description=body,
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")
    return embed
