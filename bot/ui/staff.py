"""Staff embeds and persistent role-claim panel (UI only)."""
from __future__ import annotations

import logging

import discord
from discord import ui

from bot.ui.shared import set_starlight_footer
from core.tenant import get_context

log = logging.getLogger("bot.ui.staff")

# Persistent custom_id namespace (must stay stable across deploys)
CID_WORKER = "sl_rc:worker"
CID_CUSTOMER = "sl_rc:customer"
CID_ANNOUNCE = "sl_rc:announce"
CID_GIVEAWAY = "sl_rc:giveaway"
CID_CONTENT = "sl_rc:content"


def role_claim_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎭 Role Panel",
        color=0xFFD700,
    )
    embed.description = (
        "Use the buttons below to **add** or **remove** a role on your account.\n\n"
        "### 👷 Worker\n"
        "Take order to get paid.\n\n"
        "### 🤵 Customer\n"
        "Make order to get item.\n\n"
        "### 📢 Announcements\n"
        "Pings for important server announcements.\n\n"
        "### 🎉 Giveaway\n"
        "Alerts when giveaways are running.\n\n"
        "### 🔔 Content\n"
        "Notifications for new community content."
    )
    set_starlight_footer(embed)
    return embed


def _role_id_for_custom_id(guild_id: int, custom_id: str) -> int | None:
    ctx = get_context(guild_id)
    if ctx is None:
        return None
    mapping = {
        CID_WORKER: ctx.roles.worker,
        CID_CUSTOMER: ctx.roles.customer,
        CID_ANNOUNCE: ctx.roles.announcement,
        CID_GIVEAWAY: ctx.roles.giveaway,
        CID_CONTENT: ctx.roles.content_notification,
    }
    role_id = mapping.get(custom_id)
    if role_id is None or role_id == 0:
        return None
    return role_id


class RoleClaimView(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(label="Worker", style=discord.ButtonStyle.primary, custom_id=CID_WORKER, row=0)
    async def btn_worker(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._toggle(interaction, button.custom_id)

    @ui.button(label="Customer", style=discord.ButtonStyle.primary, custom_id=CID_CUSTOMER, row=0)
    async def btn_customer(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._toggle(interaction, button.custom_id)

    @ui.button(label="Announcements", style=discord.ButtonStyle.secondary, custom_id=CID_ANNOUNCE, row=0)
    async def btn_announce(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._toggle(interaction, button.custom_id)

    @ui.button(label="Giveaway", style=discord.ButtonStyle.secondary, custom_id=CID_GIVEAWAY, row=1)
    async def btn_giveaway(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._toggle(interaction, button.custom_id)

    @ui.button(label="Content", style=discord.ButtonStyle.secondary, custom_id=CID_CONTENT, row=1)
    async def btn_content(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._toggle(interaction, button.custom_id)

    async def _toggle(self, interaction: discord.Interaction, custom_id: str | None) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return

        role_id = _role_id_for_custom_id(interaction.guild.id, custom_id or "")
        if role_id is None:
            await interaction.response.send_message("❌ Unknown button.", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message("❌ Role not found on this server.", ephemeral=True)
            return

        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Role claim panel")
                msg = f"✅ Removed role **{role.name}**."
            else:
                await member.add_roles(role, reason="Role claim panel")
                msg = f"✅ Added role **{role.name}**."
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing **Manage Roles** permission or the bot's role is below this role.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            log.warning("Role toggle failed | user=%s role=%s err=%s", member.id, role_id, exc)
            await interaction.response.send_message(
                "❌ Failed to update roles. Please try again.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(msg, ephemeral=True)
