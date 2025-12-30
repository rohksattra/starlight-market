# core/role_map.py
from __future__ import annotations
import discord

from app.domains.enums.role_enum import ServerRole
from core.config import settings


DISCORD_ROLE_MAP: dict[ServerRole, int] = {
    ServerRole.BOT_DEVELOPER: settings.BOT_DEVELOPER_ROLE_ID,
    ServerRole.BANK_MANAGER: settings.BANK_MANAGER_ROLE_ID,
    ServerRole.MODERATOR: settings.MODERATOR_ROLE_ID,
    ServerRole.WORKER: settings.WORKER_ROLE_ID,
    ServerRole.CUSTOMER: settings.CUSTOMER_ROLE_ID,
}


def has_role(member: discord.Member, role: ServerRole) -> bool:
    role_id = DISCORD_ROLE_MAP.get(role)
    return role_id is not None and role_id in {r.id for r in member.roles}


def has_any_role(member: discord.Member, roles: set[ServerRole]) -> bool:
    return any(has_role(member, role) for role in roles)


def get_discord_role(guild: discord.Guild, role: ServerRole) -> discord.Role | None:
    role_id = DISCORD_ROLE_MAP.get(role)
    return guild.get_role(role_id) if role_id else None
