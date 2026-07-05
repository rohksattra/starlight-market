from __future__ import annotations

import asyncio
import logging

import discord

from app.discord.tier_applier import apply_tier_roles
from app.repositories.user_repo import UserRepository
from app.services.tier_sync_service import resolve_tier_role_ids


log = logging.getLogger("discord.tier_role_sync")


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
        await apply_tier_roles(member, resolve_tier_role_ids(doc))

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
