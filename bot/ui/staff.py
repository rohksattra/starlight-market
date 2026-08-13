"""Staff embeds and persistent role-claim panel (UI only)."""
from __future__ import annotations

import logging

import discord
from discord import ui

from bot.ui.shared import set_starlight_footer
from core.tenant import GameContext, get_context

log = logging.getLogger("bot.ui.staff")

# Persistent custom_id namespace (must stay stable across deploys)
CID_WORKER = "sl_rc:worker"
CID_CUSTOMER = "sl_rc:customer"
CID_ANNOUNCE = "sl_rc:announce"
CID_GIVEAWAY = "sl_rc:giveaway"
CID_CONTENT = "sl_rc:content"


_RULES_COLOR = 0xFFD700
_RULES_VIOLATION_NOTE = (
    "-# Failure to follow these rules may result in a mute, kick, or ban, "
    "depending on the severity of the violation."
)


def _rule_block(number: int, title: str, body: str) -> str:
    return f"**{number}.** {title}\n{body}"


def _role_mention(role_id: int, fallback: str) -> str:
    return f"<@&{role_id}>" if role_id else fallback


def market_rules_embeds(ctx: GameContext) -> list[discord.Embed]:
    bank_manager = _role_mention(ctx.roles.bank_manager, "Bank Manager")
    moderator = _role_mention(ctx.roles.moderator, "Moderator")

    intro = discord.Embed(
        title=f"{ctx.brand.emoji} {ctx.brand.name}'s Rules",
        description=(
            "**Welcome everyone!**\n"
            "Please read these rules before using the Market. "
            "There are three categories:\n\n"
            "📜 **General Rules** — apply to everyone on this server\n"
            "⚒️ **Worker Rules** — apply to all Workers\n"
            "🛒 **Customer Rules** — apply to all Customers"
        ),
        color=_RULES_COLOR,
    )
    set_starlight_footer(intro, ctx=ctx, include_button_notice=False)

    general = discord.Embed(
        title="📜 General Rules",
        description="\n\n".join(
            [
                "These rules apply to **everyone** on this server.",
                _rule_block(
                    1,
                    "English Is the Main Language",
                    "All communication must be in English.",
                ),
                _rule_block(
                    2,
                    "Respect Others",
                    "No harassment, racism, NSFW/gore content, excessive toxicity, or spamming.",
                ),
                _rule_block(
                    3,
                    "No Unauthorized Self-Promotion",
                    "Advertising services, servers, or products is prohibited unless specifically allowed by the Market.",
                ),
                _rule_block(
                    4,
                    "Follow Procedures",
                    "Use the appropriate channels and read the instructions before asking questions.",
                ),
                _rule_block(
                    5,
                    "Respect the Staff",
                    "Staff are here to help and manage the Market, but they are not your personal assistants.",
                ),
                _rule_block(
                    6,
                    "No Off-Topic Messages in Service Channels",
                    "Keep Market channels focused on orders, claims, deliveries, and other relevant activities.",
                ),
                _rule_block(
                    7,
                    "Report Issues Privately",
                    "If you have an issue with a transaction or another user, report it to the staff through a ticket or DM.",
                ),
                _rule_block(
                    8,
                    "Do Not Share Personal Information",
                    "Do not share phone numbers, addresses, passwords, or other sensitive personal information.",
                ),
                _rule_block(
                    9,
                    "No Unauthorized Advertising",
                    "Advertising other communities, services, or streams is not allowed. "
                    "You may share your content in the designated media channel if it is relevant "
                    "and provides value to the community.",
                ),
                _RULES_VIOLATION_NOTE,
            ]
        ),
        color=_RULES_COLOR,
    )

    worker = discord.Embed(
        title="⚒️ Worker Rules",
        description="\n\n".join(
            [
                "These rules apply to all **Workers**.",
                _rule_block(
                    1,
                    "No Direct Trading with Customers",
                    f"All trades must go through the {ctx.brand.name} system. "
                    "Bypassing the Market to trade directly with Customers is strictly forbidden and may result in a ban.",
                ),
                _rule_block(
                    2,
                    "Use the Dedicated Channel for Deliveries",
                    "Once your claim is ready, notify the Bank Managers in the appropriate channel so they can arrange the pickup.",
                ),
                _rule_block(
                    3,
                    "Workers Can Place Orders",
                    "Workers may also use the Market as Customers. However, regular Customers will always have priority.",
                ),
                _rule_block(
                    4,
                    "No Stockpiling Unrequested Items",
                    "Only gather items that are listed in an active order or specifically requested by the Market.",
                ),
                _rule_block(
                    5,
                    "Quality Control Matters",
                    "Do not mix item types or deliver incorrect materials. "
                    "Repeated mistakes may result in a suspension from working with the Market.",
                ),
                _rule_block(
                    6,
                    "Faster Is Better",
                    "You have approximately 3 days to complete or update your claim. "
                    "Staff will check the progress from time to time, so make sure you claim a reasonable amount "
                    "that you can complete within the timeframe.",
                ),
                _RULES_VIOLATION_NOTE,
            ]
        ),
        color=_RULES_COLOR,
    )

    customer = discord.Embed(
        title="🛒 Customer Rules",
        description="\n\n".join(
            [
                "These rules apply to all **Customers**.",
                _rule_block(
                    1,
                    "One Order at a Time",
                    "Please place only one resource order at a time.",
                ),
                _rule_block(
                    2,
                    "No Order Size Limit",
                    "There is currently no maximum order size. However, please don't go overboard with unreasonable quantities. "
                    "The Market uses a tiered system to determine each Customer's order capacity. "
                    "Start small and work your way up to unlimited capacity.",
                ),
                _rule_block(
                    3,
                    "No Cancellation Abuse",
                    "Repeatedly cancelling orders without a valid reason may result in a temporary ban from the Market.",
                ),
                _rule_block(
                    4,
                    "Prices Follow the Market",
                    "Market prices are based on current market conditions and may change from time to time.",
                ),
                _rule_block(
                    5,
                    "Be Precise When Ordering",
                    "Only order the items and quantities you actually need. "
                    "Make sure you have enough gold to pay for the entire order.",
                ),
                _rule_block(
                    6,
                    "No Editing Orders",
                    f"If you make a mistake, please ping a {bank_manager} or {moderator} for assistance.",
                ),
                _RULES_VIOLATION_NOTE,
            ]
        ),
        color=_RULES_COLOR,
    )

    for embed in (general, worker, customer):
        set_starlight_footer(embed, ctx=ctx, include_button_notice=False)

    return [intro, general, worker, customer]


def role_claim_embed(ctx: GameContext) -> discord.Embed:
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
    set_starlight_footer(embed, ctx=ctx)
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
