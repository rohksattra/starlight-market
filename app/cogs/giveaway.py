from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.services.giveaway_service import get_giveaway_service
from utils.confirm_view import ConfirmView
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown


class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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
        if not has_any_role(interaction.user, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Only Bot Developer / Bank Manager.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="giveaway_create", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        if len(description) > 2000:
            await safe_respond(interaction, content="❌ Description is too long (max 2000 characters).", ephemeral=True)
            return

        ch = interaction.guild.get_channel(settings.GIVEAWAY_CHANNEL_ID)
        if not isinstance(ch, discord.TextChannel):
            await safe_respond(interaction, content="❌ Giveaway channel is not configured correctly.", ephemeral=True)
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

        svc = get_giveaway_service()
        gid = await svc.create_giveaway(
            self.bot,
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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiveawayCog(bot))
