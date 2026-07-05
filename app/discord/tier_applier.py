from __future__ import annotations

import logging

import discord

from app.domains.tiers import ALL_TIER_ROLE_IDS


log = logging.getLogger("discord.tier_applier")


async def apply_tier_roles(member: discord.Member, desired_role_ids: set[int]) -> None:
    if member.bot:
        return

    guild = member.guild
    if guild is None:
        return

    have = {r.id for r in member.roles}
    to_remove_ids = [rid for rid in ALL_TIER_ROLE_IDS if rid in have and rid not in desired_role_ids]
    to_add_ids = [rid for rid in desired_role_ids if rid not in have]

    roles_remove = [r for rid in to_remove_ids if (r := guild.get_role(rid)) is not None]
    roles_add = [r for rid in to_add_ids if (r := guild.get_role(rid)) is not None]

    try:
        if roles_remove:
            await member.remove_roles(*roles_remove, reason="Tier rank sync")
        if roles_add:
            await member.add_roles(*roles_add, reason="Tier rank sync")
    except discord.Forbidden:
        log.warning("Tier sync forbidden | member=%s guild=%s", member.id, guild.id)
    except discord.HTTPException:
        log.exception("Tier sync HTTP error | member=%s", member.id)
