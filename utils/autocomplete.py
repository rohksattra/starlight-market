from __future__ import annotations

from typing import List, Set

import discord
from discord import app_commands

from app.repositories.user_repo import UserRepository


users = UserRepository()
MAX_GUILD_SCAN = 200


async def user_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []

    query = current.strip().lower()
    if not query:
        return []

    results: List[app_commands.Choice[str]] = []
    seen: Set[str] = set()

    if query.isdigit():
        member = interaction.guild.get_member(int(query))
        if member and not member.bot:
            uid = str(member.id)
            results.append(
                app_commands.Choice(
                    name=f"{member.display_name} (@{member.name}) [{uid}]"[:100],
                    value=uid,
                )
            )
            seen.add(uid)

    for uid in await users.search_user_ids(query, limit=25):
        if uid in seen:
            continue
        member = interaction.guild.get_member(int(uid)) if uid.isdigit() else None
        label = (
            f"{member.display_name} (@{member.name}) [{uid}]"
            if member
            else f"Unknown [{uid}]"
        )
        results.append(app_commands.Choice(name=label[:100], value=uid))
        seen.add(uid)
        if len(results) >= 25:
            return results

    if len(results) >= 25:
        return results[:25]

    scanned = 0
    for member in interaction.guild.members:
        if member.bot:
            continue
        scanned += 1
        if scanned > MAX_GUILD_SCAN:
            break
        uid = str(member.id)
        if uid in seen:
            continue
        if query not in member.display_name.lower() and query not in member.name.lower():
            continue
        results.append(
            app_commands.Choice(
                name=f"{member.display_name} (@{member.name}) [{uid}]"[:100],
                value=uid,
            )
        )
        seen.add(uid)
        if len(results) >= 25:
            break

    return results[:25]
