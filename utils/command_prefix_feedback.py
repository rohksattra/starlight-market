# utils/command_prefix_feedback.py
from __future__ import annotations

import discord
from discord.ext import commands


async def success(ctx: commands.Context, delete_after: int = 5) -> None:
    try:
        await ctx.message.add_reaction("✅")
        await ctx.message.delete(delay=delete_after)
    except (discord.Forbidden, discord.NotFound):
        pass


async def failed(ctx: commands.Context, delete_after: int = 5) -> None:
    try:
        await ctx.message.add_reaction("❌")
        await ctx.message.delete(delay=delete_after)
    except (discord.Forbidden, discord.NotFound):
        pass
