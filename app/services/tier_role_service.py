from __future__ import annotations

import asyncio
import logging
from typing import Iterable

import discord

from core.config import settings
from app.repositories.user_repo import UserRepository

log = logging.getLogger("services.tier_role_service")

DONOR_TIER_THRESHOLDS: tuple[tuple[int, int], ...] = (
    (200_000_000, settings.ASTRALIS_DONOR_ROLE_ID),
    (125_000_000, settings.ELYSIUM_DONOR_ROLE_ID),
    (75_000_000, settings.ZENITH_DONOR_ROLE_ID),
    (40_000_000, settings.AETHER_DONOR_ROLE_ID),
    (15_000_000, settings.SANCTUM_DONOR_ROLE_ID),
    (5_000_000, settings.ORACLE_DONOR_ROLE_ID),
    (1_000_000, settings.RELIC_DONOR_ROLE_ID),
)

WORKER_TIER_THRESHOLDS: tuple[tuple[int, int], ...] = (
    (100_000_000_000, settings.GENESIS_WORKER_ROLE_ID),
    (25_000_000_000, settings.INFINITY_WORKER_ROLE_ID),
    (5_000_000_000, settings.ECLIPSE_WORKER_ROLE_ID),
    (1_000_000_000, settings.NOVA_WORKER_ROLE_ID),
    (250_000_000, settings.ASTRAL_WORKER_ROLE_ID),
    (50_000_000, settings.RANGER_WORKER_ROLE_ID),
    (10_000_000, settings.EXPLORER_WORKER_ROLE_ID),
)

CUSTOMER_TIER_THRESHOLDS: tuple[tuple[int, int], ...] = (
    (100_000_000_000, settings.CELESTIAL_CUSTOMER_ROLE_ID),
    (25_000_000_000, settings.COSMIC_CUSTOMER_ROLE_ID),
    (5_000_000_000, settings.GALACTIC_CUSTOMER_ROLE_ID),
    (1_000_000_000, settings.NEBULA_CUSTOMER_ROLE_ID),
    (250_000_000, settings.STELLAR_CUSTOMER_ROLE_ID),
    (50_000_000, settings.VOYAGER_CUSTOMER_ROLE_ID),
    (10_000_000, settings.WANDERER_CUSTOMER_ROLE_ID),
)

DONOR_ROLE_IDS: frozenset[int] = frozenset(t[1] for t in DONOR_TIER_THRESHOLDS)
WORKER_TIER_ROLE_IDS: frozenset[int] = frozenset(t[1] for t in WORKER_TIER_THRESHOLDS)
CUSTOMER_TIER_ROLE_IDS: frozenset[int] = frozenset(t[1] for t in CUSTOMER_TIER_THRESHOLDS)


def donor_role_for_total(donation_total: int) -> int | None:
    for threshold, role_id in DONOR_TIER_THRESHOLDS:
        if donation_total >= threshold:
            return role_id
    return None


def worker_tier_role_for_income(income: int) -> int | None:
    for threshold, role_id in WORKER_TIER_THRESHOLDS:
        if income >= threshold:
            return role_id
    return None


def customer_tier_role_for_spent(spent: int) -> int | None:
    for threshold, role_id in CUSTOMER_TIER_THRESHOLDS:
        if spent >= threshold:
            return role_id
    return None


class TierRoleService:
    def __init__(self) -> None:
        self.users = UserRepository()

    async def sync_member(self, member: discord.Member) -> None:
        if member.bot:
            return
        doc = await self.users.get_user(str(member.id))
        if not doc:
            await self.users.ensure_user(str(member.id))
            doc = await self.users.get_user(str(member.id)) or {}

        donation = int(doc.get("donation_given") or 0)
        worker_income = int(doc.get("total_worker_income") or 0)
        customer_spent = int(doc.get("total_customer_spent") or 0)

        await self._sync_category(member, DONOR_ROLE_IDS, donor_role_for_total(donation))
        await self._sync_category(member, WORKER_TIER_ROLE_IDS, worker_tier_role_for_income(worker_income))
        await self._sync_category(member, CUSTOMER_TIER_ROLE_IDS, customer_tier_role_for_spent(customer_spent))

    async def _sync_category(
        self,
        member: discord.Member,
        all_tier_ids: Iterable[int],
        chosen_role_id: int | None,
    ) -> None:
        guild = member.guild
        if guild is None:
            return
        have = {r.id for r in member.roles}
        tier_set = frozenset(all_tier_ids)
        to_remove_ids = [rid for rid in tier_set if rid in have and rid != chosen_role_id]
        roles_remove = [r for rid in to_remove_ids if (r := guild.get_role(rid)) is not None]
        role_add = guild.get_role(chosen_role_id) if chosen_role_id and chosen_role_id not in have else None

        try:
            if roles_remove:
                await member.remove_roles(*roles_remove, reason="Tier rank sync")
            if role_add:
                await member.add_roles(role_add, reason="Tier rank sync")
        except discord.Forbidden:
            log.warning("Tier sync forbidden | member=%s guild=%s", member.id, guild.id)
        except discord.HTTPException:
            log.exception("Tier sync HTTP error | member=%s", member.id)


def schedule_member_tier_sync(guild: discord.Guild, user_id: str) -> None:
    """Non-blocking tier sync after /income or manual paid/spent."""

    async def _run() -> None:
        try:
            member = guild.get_member(int(user_id))
            if member and not member.bot:
                await TierRoleService().sync_member(member)
        except Exception:
            log.exception("Background tier sync failed | user_id=%s", user_id)

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        log.warning("No running loop for tier sync | user_id=%s", user_id)
