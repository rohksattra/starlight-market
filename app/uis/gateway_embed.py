# app/uis/gateway_embed.py
from __future__ import annotations

import discord


def welcome_embed(member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        description=(
            f"Hello, {member.mention}!\n"
            f"👋 Welcome to **{member.guild.name}**!\n"
            "We're glad to have you here ✨"
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def farewell_embed(member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        description=(
            f"**{member.mention}** has left the server.\n"
            "We wish you the best on your next journey 🚀"
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed
