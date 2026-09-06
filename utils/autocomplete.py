"""Tenant-aware Discord slash autocomplete helpers."""
from __future__ import annotations

from typing import Set

import discord
from discord import app_commands

from core.tenant import get_context

AUTOCOMPLETE_LIMIT = 25


def member_label(member: discord.Member) -> str:
    return f"{member.display_name} (@{member.name}) [{member.id}]"


def fallback_user_label(user_id: str) -> str:
    return f"User [{user_id}]"


def _member_choice(member: discord.Member) -> app_commands.Choice[str]:
    return app_commands.Choice(
        name=member_label(member)[:100],
        value=str(member.id),
    )


def _fallback_choice(user_id: str) -> app_commands.Choice[str]:
    return app_commands.Choice(
        name=fallback_user_label(user_id)[:100],
        value=user_id,
    )


def _member_matches(member: discord.Member, query: str) -> bool:
    if not query:
        return True
    q = query.lower()
    return q in member.display_name.lower() or q in member.name.lower() or q in str(member.id)


async def user_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []

    if get_context(interaction.guild.id) is None:
        return []

    guild = interaction.guild
    query = current.strip()
    results: list[app_commands.Choice[str]] = []
    seen: Set[str] = set()

    def add_member(member: discord.Member) -> None:
        if member.bot:
            return
        uid = str(member.id)
        if uid in seen:
            return
        results.append(_member_choice(member))
        seen.add(uid)

    if query.isdigit():
        member = guild.get_member(int(query))
        if member and not member.bot:
            add_member(member)
        else:
            results.append(_fallback_choice(query))
            seen.add(query)
        if len(results) >= AUTOCOMPLETE_LIMIT:
            return results[:AUTOCOMPLETE_LIMIT]

    for member in guild.members:
        if len(results) >= AUTOCOMPLETE_LIMIT:
            break
        if member.bot or not _member_matches(member, query):
            continue
        add_member(member)

    return results[:AUTOCOMPLETE_LIMIT]
