from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.domains.tiers import donor_role_for_total
from app.services.economy.donation_service import DonationService
from app.discord.tier_role_sync import TierRoleService
from app.views.donation_embed import donation_embed
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown
from utils.autocomplete import user_autocomplete
from utils.confirm_view import ConfirmView


log = logging.getLogger("cogs.donation")


class DonationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = DonationService()
        self.tiers = TierRoleService()

    def _is_allowed(self, member: discord.Member) -> bool:
        return has_any_role(member, ORDER_MANAGEMENT_ROLES)

    @app_commands.command(name="donation", description="(Staff) Record a donation (gold or item value)")
    @app_commands.describe(
        user="Member who donated",
        gold="Gold amount or estimated item value",
        description="Donation or item details",
    )
    @app_commands.autocomplete(user=user_autocomplete)
    async def donation(
        self,
        interaction: discord.Interaction,
        user: str,
        gold: app_commands.Range[int, 1, 2_147_483_647],
        description: str,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid context.", ephemeral=True)
            return

        if not self._is_allowed(interaction.user):
            await safe_respond(interaction, content="❌ Only Bot Developer / Bank Manager.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="donation", seconds=3)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        if not user.isdigit():
            await safe_respond(interaction, content="❌ Invalid user ID.", ephemeral=True)
            return

        donor_member = interaction.guild.get_member(int(user))
        if donor_member is None:
            await safe_respond(interaction, content="❌ Member not found in this server.", ephemeral=True)
            return

        if len(description) > 2000:
            await safe_respond(interaction, content="❌ Description is too long (max 2000 characters).", ephemeral=True)
            return

        donor_label = donor_member.display_name if donor_member else f"User [{user}]"

        confirm_embed = discord.Embed(
            title="Confirm Donation",
            description=(
                "Please review the details below.\n"
                "Click **Confirm** to record the donation, or **Cancel**."
            ),
            color=0xFFD700,
        )
        confirm_embed.add_field(name="Donor", value=donor_label, inline=True)
        confirm_embed.add_field(name="Gold", value=f"{gold:,}", inline=True)
        confirm_embed.add_field(name="Description", value=description.strip()[:1000], inline=False)

        view = ConfirmView(author_id=interaction.user.id, timeout_seconds=30)
        await safe_respond(interaction, embed=confirm_embed, view=view, ephemeral=True)

        confirmed = await view.wait_result()
        if not confirmed:
            await safe_respond(interaction, content="❌ Donation cancelled.", ephemeral=True)
            return

        doc = await self.service.record(user_id=user, gold=gold)

        await self.tiers.sync_member(donor_member)

        donation_total = int(doc.get("donation_given", 0) or 0) if doc else 0
        donor_tier_role_id = donor_role_for_total(donation_total)

        ch = interaction.guild.get_channel(settings.MARKET_DONATION_CHANNEL_ID)

        if isinstance(ch, discord.TextChannel):
            embed = donation_embed(
                user_id=user,
                gold=gold,
                description=description,
                donor_tier_role_id=donor_tier_role_id,
            )

            try:
                await ch.send(embed=embed)
            except discord.HTTPException:
                log.exception("Failed to send donation embed | channel=%s", ch.id)

        await safe_respond(
            interaction,
            content="✅ Donation recorded and embed posted.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DonationCog(bot))