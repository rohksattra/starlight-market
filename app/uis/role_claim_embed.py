from __future__ import annotations

import discord

from app.uis.embed_footer import set_starlight_footer


def role_claim_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎭 Role Panel",
        color=0xFFD700,
    )
    embed.description = (
        "Use the buttons below to **add** or **remove** a role on your account.\n\n"
        "### 👷 Worker\n"
        "Take order to get paid.\n\n"
        "### 🤵 Customer\n"
        "Make order to get item.\n\n"
        "### 📢 Announcements\n"
        "Pings for important server announcements.\n\n"
        "### 🎉 Giveaway\n"
        "Alerts when giveaways are running.\n\n"
        "### 🔔 Content\n"
        "Notifications for new community content."
    )
    set_starlight_footer(embed)
    return embed
