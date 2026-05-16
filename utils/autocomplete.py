from __future__ import annotations

import re
from typing import List, Set

import discord
from discord import app_commands

from app.repositories.user_repo import UserRepository


users = UserRepository()


async def user_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []

    query = current.strip().lower()

    results: List[app_commands.Choice[str]] = []
    seen: Set[str] = set()

    for member in interaction.guild.members:
        if member.bot:
            continue

        uid = str(member.id)

        if (query in member.display_name.lower() or query in member.name.lower() or query in uid):
            results.append(
                app_commands.Choice(
                    name=f"{member.display_name} (@{member.name}) [{uid}]"[:100],
                    value=uid,
                )
            )

            seen.add(uid)

            if len(results) >= 20:
                break

    if current.strip():
        safe_query = re.escape(current.strip())

        docs = await users.users.find(
            {"user_id": {"$regex": safe_query}},
            {"user_id": 1},
        ).to_list(20)

        for doc in docs:
            uid = str(doc["user_id"])

            if uid in seen:
                continue

            member = interaction.guild.get_member(int(uid)) if uid.isdigit() else None

            if member:
                label = f"{member.display_name} (@{member.name}) [{uid}]"
            else:
                label = f"Unknown [{uid}]"

            results.append(
                app_commands.Choice(
                    name=label[:100],
                    value=uid,
                )
            )

            seen.add(uid)

            if len(results) >= 25:
                break

    return results[:25]