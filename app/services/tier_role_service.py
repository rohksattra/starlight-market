from __future__ import annotations

import asyncio
import logging
import discord

from core.config import settings
from app.repositories.user_repo import UserRepository

log = logging.getLogger("services.tier_role_service")

DONOR_TIER_THRESHOLDS: tuple[tuple[int, int], ...] = (
    (1_000_000_000, settings.ASTRALIS_DONOR_ROLE_ID),
    (500_000_000, settings.ELYSIUM_DONOR_ROLE_ID),
    (250_000_000, settings.ZENITH_DONOR_ROLE_ID),
    (100_000_000, settings.AETHER_DONOR_ROLE_ID),
    (50_000_000, settings.SANCTUM_DONOR_ROLE_ID),
    (20_000_000, settings.ORACLE_DONOR_ROLE_ID),
    (5_000_000, settings.RELIC_DONOR_ROLE_ID),
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

ALL_TIER_ROLE_IDS: frozenset[int] = DONOR_ROLE_IDS | WORKER_TIER_ROLE_IDS | CUSTOMER_TIER_ROLE_IDS


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
        await self.sync_member_with_doc(member, doc)

    async def sync_member_with_doc(self, member: discord.Member, doc: dict) -> None:
        if member.bot:
            return
        guild = member.guild
        if guild is None:
            return

        donation = int(doc.get("donation_given") or 0)
        worker_income = int(doc.get("total_worker_income") or 0)
        customer_spent = int(doc.get("total_customer_spent") or 0)

        chosen_donor = donor_role_for_total(donation)
        chosen_worker = worker_tier_role_for_income(worker_income)
        chosen_customer = customer_tier_role_for_spent(customer_spent)
        desired = {rid for rid in (chosen_donor, chosen_worker, chosen_customer) if rid is not None}

        have = {r.id for r in member.roles}
        to_remove_ids = [rid for rid in ALL_TIER_ROLE_IDS if rid in have and rid not in desired]
        to_add_ids = [rid for rid in desired if rid not in have]

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

    async def bulk_sync_guild(
        self,
        guild: discord.Guild,
        *,
        concurrency: int = 12,
        chunk_members: bool = True,
    ) -> dict[str, int]:
        if chunk_members:
            await guild.chunk(cache=True)

        members = [m for m in guild.members if not m.bot]
        ids = [str(m.id) for m in members]
        user_map: dict[str, dict] = {}
        batch_size = 500
        for i in range(0, len(ids), batch_size):
            chunk = ids[i : i + batch_size]
            user_map.update(await self.users.find_users_by_ids(chunk))

        sem = asyncio.Semaphore(concurrency)

        async def one(mem: discord.Member) -> None:
            async with sem:
                doc = user_map.get(str(mem.id), {})
                await self.sync_member_with_doc(mem, doc)

        results = await asyncio.gather(*(one(m) for m in members), return_exceptions=True)
        errors = sum(1 for r in results if isinstance(r, BaseException))
        return {"members": len(members), "errors": errors}


def schedule_member_tier_sync(guild: discord.Guild, user_id: str) -> None:
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
