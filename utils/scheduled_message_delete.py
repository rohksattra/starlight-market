from __future__ import annotations

import asyncio
import logging

import discord


log = logging.getLogger("utils.scheduled_message_delete")

GAME_ANSWER_DELETE_AFTER_SECONDS = 180


def schedule_message_delete(
    message: discord.Message,
    *,
    delay_seconds: int = GAME_ANSWER_DELETE_AFTER_SECONDS,
) -> None:
    async def _delete_later() -> None:
        try:
            await asyncio.sleep(max(0, delay_seconds))
            await message.delete()
        except discord.NotFound:
            return
        except discord.Forbidden:
            log.debug(
                "Cannot delete message | channel=%s message=%s",
                message.channel.id,
                message.id,
            )
        except discord.HTTPException:
            log.warning(
                "Failed to delete message | channel=%s message=%s",
                message.channel.id,
                message.id,
            )

    asyncio.create_task(_delete_later())
