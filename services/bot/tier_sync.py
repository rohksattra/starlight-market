"""Resolve and apply Discord tier roles from user economy totals."""
from __future__ import annotations

import asyncio
import logging

import discord

from core.tenant import GameContext, get_context
from services.profile import ProfileService
from services.tiers import (
    customer_tier_for_spent,
    donor_tier_for_total,
    worker_tier_for_income,
)

log = logging.getLogger("bot.tier_sync")


def all_tier_role_ids(ctx: GameContext) -> set[int]:
    return {
        rid
        for mapping in (ctx.roles.donor_tiers, ctx.roles.worker_tiers, ctx.roles.customer_tiers)
        for rid in mapping.values()
        if rid
    }


def resolve_tier_role_ids(doc: dict, ctx: GameContext) -> set[int]:
    donation = int(doc.get("donation_given") or 0)
    worker_income = int(doc.get("total_worker_income") or 0)
    customer_spent = int(doc.get("total_customer_spent") or 0)

    chosen: set[int] = set()

    donor_name = donor_tier_for_total(donation, game=ctx.game)
    if donor_name:
        rid = ctx.roles.donor_tiers.get(donor_name)
        if rid:
            chosen.add(rid)

    worker_name = worker_tier_for_income(worker_income, game=ctx.game)
    if worker_name:
        rid = ctx.roles.worker_tiers.get(worker_name)
        if rid:
            chosen.add(rid)

    customer_name = customer_tier_for_spent(customer_spent, game=ctx.game)
    if customer_name:
        rid = ctx.roles.customer_tiers.get(customer_name)
        if rid:
            chosen.add(rid)

    return chosen


async def apply_tier_roles(
    member: discord.Member,
    desired_role_ids: set[int],
    *,
    all_tier_ids: set[int],
) -> None:
    if member.bot:
        return

    guild = member.guild
    if guild is None:
        return

    have = {r.id for r in member.roles}
    to_remove_ids = [rid for rid in all_tier_ids if rid in have and rid not in desired_role_ids]
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


class TierRoleService:
    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self.profiles = ProfileService(ctx)
        self._all_tier_ids = all_tier_role_ids(ctx)

    async def sync_member(self, member: discord.Member) -> None:
        if member.bot:
            return
        doc = await self.profiles.get_or_ensure_user(str(member.id))
        await self.sync_member_with_doc(member, doc)

    async def sync_member_with_doc(self, member: discord.Member, doc: dict) -> None:
        await apply_tier_roles(
            member,
            resolve_tier_role_ids(doc, self.ctx),
            all_tier_ids=self._all_tier_ids,
        )


def schedule_member_tier_sync(guild: discord.Guild, user_id: str, ctx: GameContext | None = None) -> None:
    tenant = ctx or get_context(guild.id)
    if tenant is None:
        return

    async def _run() -> None:
        try:
            member = guild.get_member(int(user_id))
            if member and not member.bot:
                await TierRoleService(tenant).sync_member(member)
        except Exception:
            log.exception("Background tier sync failed | user_id=%s", user_id)

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        log.warning("No running loop for tier sync | user_id=%s", user_id)
