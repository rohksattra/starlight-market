"""Role checks using GameContext role IDs."""
from __future__ import annotations

import discord

from core.tenant import GameContext
from models.enums import ServerRole


def has_role(member: discord.Member, ctx: GameContext, role: ServerRole) -> bool:
    role_id = _resolve_role_id(ctx, role)
    if role_id == 0:
        return False
    return any(r.id == role_id for r in member.roles)


def has_any_role(member: discord.Member, ctx: GameContext, roles: set[ServerRole] | frozenset[ServerRole]) -> bool:
    return any(has_role(member, ctx, role) for role in roles)


def _resolve_role_id(ctx: GameContext, role: ServerRole) -> int:
    roles = ctx.roles
    mapping = {
        ServerRole.BOT_DEVELOPER: roles.bot_developer,
        ServerRole.BANK_MANAGER: roles.bank_manager,
        ServerRole.MODERATOR: roles.moderator,
        ServerRole.WORKER: roles.worker,
        ServerRole.CUSTOMER: roles.customer,
    }
    return mapping[role]
