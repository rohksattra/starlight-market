from __future__ import annotations

from typing import List, Set

import discord
from discord import app_commands

from app.repositories.user_repo import UserRepository


users = UserRepository()


def member_label(member: discord.Member) -> str:
    return f"{member.display_name} (@{member.name}) [{member.id}]"


def fallback_user_label(user_id: str) -> str:
    return f"User [{user_id}]"


def _matches_query(*, query: str, label: str, user_id: str) -> bool:
    if not query:
        return True
    q = query.lower()
    return q in label.lower() or q in user_id


def _member_choice(member: discord.Member) -> app_commands.Choice[str]:
    uid = str(member.id)
    return app_commands.Choice(
        name=member_label(member)[:100],
        value=uid,
    )


def _fallback_choice(user_id: str) -> app_commands.Choice[str]:
    return app_commands.Choice(
        name=fallback_user_label(user_id)[:100],
        value=user_id,
    )


async def user_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []

    guild = interaction.guild
    query = current.strip().lower()
    results: List[app_commands.Choice[str]] = []
    seen: Set[str] = set()

    if query.isdigit():
        member = guild.get_member(int(query))
        if member and not member.bot:
            uid = str(member.id)
            results.append(_member_choice(member))
            seen.add(uid)
        elif query not in seen:
            results.append(_fallback_choice(query))
            seen.add(query)

    if query:
        for uid in await users.search_user_ids(query, limit=25):
            if uid in seen:
                continue
            member = guild.get_member(int(uid)) if uid.isdigit() else None
            label = member_label(member) if member else fallback_user_label(uid)
            if not _matches_query(query=query, label=label, user_id=uid):
                continue
            results.append(app_commands.Choice(name=label[:100], value=uid))
            seen.add(uid)
            if len(results) >= 25:
                return results

    for member in sorted(
        (m for m in guild.members if not m.bot),
        key=lambda m: m.display_name.lower(),
    ):
        uid = str(member.id)
        if uid in seen:
            continue
        if query and query not in member.display_name.lower() and query not in member.name.lower():
            continue
        results.append(_member_choice(member))
        seen.add(uid)
        if len(results) >= 25:
            break

    return results[:25]
