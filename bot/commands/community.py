"""Slash & prefix commands for community features (giveaway, minfo, games)."""
from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.handlers.community import get_community_handler
from bot.handlers.games import channel_id_for_game, get_game_handler
from bot.ui.community import slinfo_embeds
from core.tenant import get_context
from models.enums import ORDER_MANAGEMENT_ROLES, STAFF_ROLES
from models.games import PLAYABLE_GAME_TYPES, PlayableGameType
from utils.confirm_view import ConfirmView
from utils.cooldown import check_cooldown
from utils.discord_safe import safe_defer, safe_respond
from utils.permissions import has_any_role
from utils.prefix_feedback import failed, success

SLINFO_DELETE_AFTER_SECONDS = 300


class CommunityCommands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.handler = get_community_handler()
        self.game = get_game_handler(bot)

    @app_commands.command(name="giveaway", description="(Staff) Post a giveaway to the giveaway channel")
    @app_commands.describe(
        host="Giveaway host (shown on the panel)",
        winners="Number of winners to draw",
        hours="Duration in hours before entries close",
        description="Prize / rules description",
    )
    async def giveaway(
        self,
        interaction: discord.Interaction,
        host: discord.Member,
        winners: app_commands.Range[int, 1, 25],
        hours: app_commands.Range[int, 1, 720],
        description: str,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Guild only.", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Only Bot Developer / Bank Manager.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="giveaway_create", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        if len(description) > 2000:
            await safe_respond(
                interaction,
                content="❌ Description is too long (max 2000 characters).",
                ephemeral=True,
            )
            return

        ch = interaction.guild.get_channel(ctx.channels.giveaway)
        if not isinstance(ch, discord.TextChannel):
            await safe_respond(
                interaction,
                content="❌ Giveaway channel is not configured correctly.",
                ephemeral=True,
            )
            return

        confirm_embed = discord.Embed(
            title="Confirm Giveaway",
            description=(
                "Please review the details below.\n"
                "Click **Confirm** to post the giveaway, or **Cancel**."
            ),
            color=0xFFD700,
        )
        confirm_embed.add_field(name="Channel", value=ch.mention, inline=False)
        confirm_embed.add_field(name="Host", value=host.mention, inline=True)
        confirm_embed.add_field(name="Winners", value=str(int(winners)), inline=True)
        confirm_embed.add_field(name="Duration", value=f"{int(hours)} hour(s)", inline=True)
        confirm_embed.add_field(name="Description", value=description.strip()[:1000], inline=False)

        view = ConfirmView(author_id=interaction.user.id, timeout_seconds=30)
        await safe_respond(interaction, embed=confirm_embed, view=view, ephemeral=True)

        confirmed = await view.wait_result()
        if not confirmed:
            await safe_respond(interaction, content="❌ Giveaway cancelled.", ephemeral=True)
            return

        gid = await self.handler.create_giveaway(
            self.bot,
            ctx=ctx,
            guild=interaction.guild,
            channel=ch,
            host=host,
            winner_count=int(winners),
            hours=int(hours),
            prize_description=description.strip(),
        )
        if gid is None:
            await safe_respond(interaction, content="❌ Failed to post the giveaway.", ephemeral=True)
            return

        await safe_respond(
            interaction,
            content=f"✅ Giveaway posted in {ch.mention}.",
            ephemeral=True,
        )

    @commands.command(name="minfo")
    async def minfo(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            await failed(ctx)
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="minfo", seconds=5)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            await failed(ctx)
            return

        for embed in slinfo_embeds(ctx=tenant, bot_user=self.bot.user):
            await ctx.send(embed=embed, delete_after=SLINFO_DELETE_AFTER_SECONDS)

        await success(ctx)

    @app_commands.command(
        name="game-panel",
        description="Post a persistent game panel to its configured channel.",
    )
    @app_commands.describe(game="Game panel to post")
    @app_commands.choices(
        game=[
            app_commands.Choice(name="Counting", value="counting"),
            app_commands.Choice(name="Word Chain", value="wordchain"),
            app_commands.Choice(name="Scramble Word", value="scramble"),
            app_commands.Choice(name="Monster Hunt", value="monster"),
            app_commands.Choice(name="Boss Battle", value="boss"),
        ]
    )
    async def game_panel(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
    ) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(
                interaction,
                content="❌ Use this command in a server.",
                ephemeral=True,
            )
            return

        tenant = get_context(interaction.guild.id)
        if tenant is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, tenant, STAFF_ROLES):
            await safe_respond(
                interaction,
                content="❌ You don't have permission to use this command.",
                ephemeral=True,
            )
            return

        game_type = cast(PlayableGameType, game.value)
        if game_type not in PLAYABLE_GAME_TYPES:
            await safe_respond(interaction, content="❌ Unknown game type.", ephemeral=True)
            return

        channel_id = channel_id_for_game(tenant, game_type)
        channel = interaction.guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            await safe_respond(
                interaction,
                content=f"❌ Channel for **{game.name}** is not configured or not found.",
                ephemeral=True,
            )
            return

        await safe_defer(interaction, ephemeral=True)
        await self.game.send_game_panel(channel=channel, ctx=tenant, game_type=game_type)
        await safe_respond(
            interaction,
            content=f"✅ **{game.name}** panel posted in {channel.mention}.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityCommands(bot))
