from __future__ import annotations

import logging
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from core.config import settings
from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.repositories.user_repo import UserRepository
from app.services.tier_role_service import TierRoleService, donor_role_for_total
from app.uis.donation_embed import donation_embed
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown

log = logging.getLogger("cogs.donation")


class DonationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.users = UserRepository()
        self.tiers = TierRoleService()

    def _is_allowed(self, member: discord.Member) -> bool:
        return has_any_role(member, ORDER_MANAGEMENT_ROLES)

    async def user_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []

        current_lower = current.lower()
        results: List[app_commands.Choice[str]] = []
        seen_ids: set[str] = set()

        for member in interaction.guild.members:
            display = member.display_name.lower()
            username = member.name.lower()
            if current_lower in display or current_lower in username:
                uid = str(member.id)
                label = f"{member.display_name} (@{member.name}) [{uid}]"
                results.append(app_commands.Choice(name=label[:100], value=uid))
                seen_ids.add(uid)
            if len(results) >= 20:
                break

        docs = []
        if current.strip():
            docs = await self.users.users.find({"user_id": {"$regex": current}}, {"user_id": 1}).to_list(20)
        for d in docs:
            uid = d.get("user_id")
            if not uid or uid in seen_ids:
                continue
            try:
                member = interaction.guild.get_member(int(uid))
            except (ValueError, TypeError):
                member = None
            if member:
                label = f"{member.display_name} (@{member.name}) [{uid}]"
            else:
                label = f"Unknown [{uid}]"
            results.append(app_commands.Choice(name=label[:100], value=uid))
            seen_ids.add(uid)
            if len(results) >= 25:
                break

        return results[:25]

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

        if len(description) > 2000:
            await safe_respond(interaction, content="❌ Description is too long (max 2000 characters).", ephemeral=True)
            return

        await self.users.ensure_user(user)
        await self.users.inc_donation_given(user_id=user, amount=gold)

        donor_member = interaction.guild.get_member(int(user)) if user.isdigit() else None
        if donor_member:
            await self.tiers.sync_member(donor_member)

        doc = await self.users.get_user(user)
        donation_total = int(doc.get("donation_given", 0) or 0) if doc else 0
        donor_tier_role_id = donor_role_for_total(donation_total)

        ch = interaction.guild.get_channel(settings.MARKET_DONATION_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            embed = donation_embed(
                donor_id=user,
                gold=gold,
                description=description,
                donor_tier_role_id=donor_tier_role_id,
            )
            try:
                await ch.send(embed=embed)
            except discord.HTTPException:
                log.exception("Failed to send donation embed | channel=%s", ch.id)

        await safe_respond(interaction, content="✅ Donation recorded and embed posted.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DonationCog(bot))
