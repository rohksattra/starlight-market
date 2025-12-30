# app/services/server_service.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import discord

from core.role_map import has_any_role
from app.domains.enums.role_enum import STAFF_ROLE


log = logging.getLogger("services.server_service")

DISCORD_BULK_DELETE_LIMIT = 100
DISCORD_MESSAGE_MAX_AGE = timedelta(days=14)


class ServerService:
    def _validate_quantity(self, quantity: int) -> None:
        if quantity <= 0 or quantity > DISCORD_BULK_DELETE_LIMIT:
            raise ValueError(f"Quantity must be between 1 and {DISCORD_BULK_DELETE_LIMIT}")

    def ensure_allowed(self, member: discord.Member) -> None:
        if not has_any_role(member, STAFF_ROLE):
            log.warning("Permission denied | user=%s", member.id)
            raise PermissionError("You don't have permission to use this command.")

    async def delete_messages(self, *, channel: discord.TextChannel, quantity: int) -> int:
        self._validate_quantity(quantity)
        min_time = datetime.now(timezone.utc) - DISCORD_MESSAGE_MAX_AGE
        messages: List[discord.Message] = []
        async for msg in channel.history(limit=quantity):
            if msg.pinned or msg.created_at < min_time:
                continue
            messages.append(msg)
        if not messages:
            log.warning("Delete messages failed | none deletable | channel=%s qty=%s", channel.id, quantity)
            raise ValueError("No messages can be deleted (older than 14 days or pinned).")
        await channel.delete_messages(messages)
        log.info("Messages deleted | channel=%s count=%s", channel.id, len(messages))
        return len(messages)
