# app/cogs/profile.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from app.services.profile_service import ProfileService
from app.uis.profile_embed import profile_embed
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown


class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.profile_serv = ProfileService()

    @commands.command(name="me")
    async def me(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return
        try:
            check_cooldown(user_id=ctx.author.id, key="profile_me", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            return
        await self._send_profile(ctx, ctx.author)
        try:
            await ctx.message.add_reaction("✅")
            await ctx.message.delete(delay=5)
        except discord.Forbidden:
            pass

    @app_commands.command(name="profile", description="View a member profile")
    @app_commands.describe(member="Select a member")
    async def profile(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return
        try:
            check_cooldown(user_id=interaction.user.id, key="profile_view", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        await safe_defer(interaction, ephemeral=False)
        await self._send_profile(interaction, member)

    async def _send_profile(self, ctx_or_interaction: commands.Context | discord.Interaction, member: discord.Member) -> None:
        data = await self.profile_serv.get_profile_data(user_id=str(member.id))
        embed = profile_embed(member=member, **data)
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(embed=embed)
        else:
            await safe_respond(ctx_or_interaction, embed=embed, ephemeral=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
