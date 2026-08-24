"""Slash & prefix commands for market features (profile, panels, paid/spent)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.commands.market_economy import MarketEconomyMixin
from bot.commands.market_panels import MarketPanelMixin
from bot.handlers.market import get_market_handler
from bot.ui.market import profile_embed
from core.tenant import GameContext, get_context
from services.profile import ProfileService
from utils.cooldown import check_cooldown
from utils.discord_safe import safe_defer, safe_respond
from utils.prefix_feedback import failed, success


class MarketCommands(MarketPanelMixin, MarketEconomyMixin, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.handler = get_market_handler()

    @commands.command(name="mme")
    async def me(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            await failed(ctx)
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="profile_me", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return

        await self._send_profile(ctx, ctx.author, tenant)
        await success(ctx)

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

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        await safe_defer(interaction, ephemeral=True)
        await self._send_profile(interaction, member, ctx)

    async def _send_profile(
        self,
        ctx_or_interaction: commands.Context | discord.Interaction,
        member: discord.Member,
        tenant: GameContext,
    ) -> None:
        data = await ProfileService(tenant).get_profile_data(user_id=str(member.id))
        embed = profile_embed(member=member, ctx=tenant, **data)

        if isinstance(ctx_or_interaction, commands.Context):
            guild = ctx_or_interaction.guild
            channel = guild.get_channel(tenant.channels.user_profile) if guild else None
            target = channel if isinstance(channel, discord.TextChannel) else ctx_or_interaction.channel
            await target.send(embed=embed)
            return

        guild = ctx_or_interaction.guild
        channel = guild.get_channel(tenant.channels.user_profile) if guild else None
        if isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed)
            await safe_respond(
                ctx_or_interaction,
                content=f"✅ Profile sent to {channel.mention}.",
                ephemeral=True,
            )
            return

        await ctx_or_interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MarketCommands(bot))
