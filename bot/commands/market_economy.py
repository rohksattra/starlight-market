"""Staff donation / paid / spent slash commands."""
from __future__ import annotations

import logging
from typing import List

import discord
from discord import app_commands

from bot.activity_log import log_activity, person_name
from bot.handlers.orders import post_transaction_embed
from bot.tier_sync import TierRoleService, schedule_member_tier_sync
from bot.ui.market import donation_embed
from core.tenant import get_context
from models.enums import ORDER_MANAGEMENT_ROLES
from services.economy import EconomyService
from services.items import ItemService
from services.tiers import donor_tier_for_total
from utils.autocomplete import fallback_user_label, user_autocomplete
from utils.confirm_view import ConfirmView
from utils.cooldown import check_cooldown
from utils.discord_safe import safe_defer, safe_respond
from utils.permissions import has_any_role

log = logging.getLogger("bot.commands.market")


async def item_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []
    ctx = get_context(interaction.guild.id)
    if ctx is None:
        return []

    items = await ItemService(ctx).list_items()
    results: List[app_commands.Choice[str]] = []
    for item in items:
        name = item.get("item_name", "")
        if current.lower() in name.lower():
            results.append(app_commands.Choice(name=name[:100], value=item["item_id"]))
        if len(results) >= 25:
            break
    return results


class MarketEconomyMixin:
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

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
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

        confirm_embed = discord.Embed(
            title="Confirm Donation",
            description=(
                "Please review the details below.\n"
                "Click **Confirm** to record the donation, or **Cancel**."
            ),
            color=0xFFD700,
        )
        confirm_embed.add_field(name="Donor", value=donor_member.display_name, inline=True)
        confirm_embed.add_field(name="Gold", value=f"{gold:,}", inline=True)
        confirm_embed.add_field(name="Description", value=description.strip()[:1000], inline=False)

        view = ConfirmView(author_id=interaction.user.id, timeout_seconds=30)
        await safe_respond(interaction, embed=confirm_embed, view=view, ephemeral=True)

        confirmed = await view.wait_result()
        if not confirmed:
            await safe_respond(interaction, content="❌ Donation cancelled.", ephemeral=True)
            return

        doc = await EconomyService(ctx).record_donation(user_id=user, gold=gold)
        await TierRoleService(ctx).sync_member(donor_member)

        donation_total = int(doc.get("donation_given", 0) or 0) if doc else 0
        donor_tier_name = donor_tier_for_total(donation_total, game=ctx.game)
        donor_tier_role_id = (
            ctx.roles.donor_tiers.get(donor_tier_name) if donor_tier_name else None
        )

        ch = interaction.guild.get_channel(ctx.channels.donation)
        if isinstance(ch, discord.TextChannel):
            embed = donation_embed(
                user_id=user,
                gold=gold,
                description=description,
                donor_tier_role_id=donor_tier_role_id,
                ctx=ctx,
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
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=f"Added donation of {gold:,} gold for {donor_member.display_name}",
        )

    @app_commands.command(name="paid", description="(Staff) Add manual worker income")
    @app_commands.autocomplete(user=user_autocomplete, item=item_autocomplete)
    async def paid(
        self,
        interaction: discord.Interaction,
        user: str,
        item: str,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid context.", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Only Bot Developer / Bank Manager.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="paid", seconds=3)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        item_doc = await ItemService(ctx).get_by_id(item)
        if not item_doc:
            await safe_respond(interaction, content="❌ Item not found.", ephemeral=True)
            return

        member = interaction.guild.get_member(int(user)) if user.isdigit() else None
        user_label = member.display_name if member else fallback_user_label(user)
        item_name = item_doc.get("item_name", item)

        confirm_embed = discord.Embed(
            title="Confirm Paid",
            description=(
                "Please review the details below.\n"
                "Click **Confirm** to record worker income, or **Cancel**."
            ),
            color=0xFFD700,
        )
        confirm_embed.add_field(name="Worker", value=user_label, inline=True)
        confirm_embed.add_field(name="Item", value=item_name, inline=True)
        confirm_embed.add_field(name="Quantity", value=str(quantity), inline=True)

        view = ConfirmView(author_id=interaction.user.id, timeout_seconds=30)
        await safe_respond(interaction, embed=confirm_embed, view=view, ephemeral=True)

        confirmed = await view.wait_result()
        if not confirmed:
            await safe_respond(interaction, content="❌ Paid cancelled.", ephemeral=True)
            return

        try:
            result = await EconomyService(ctx).paid_worker(
                user_id=user,
                item_id=item,
                quantity=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        schedule_member_tier_sync(interaction.guild, user, ctx)
        await post_transaction_embed(
            guild=interaction.guild,
            ctx=ctx,
            target="worker",
            member=member,
            item_name=str(result["item_name"]),
            item_price=int(result["item_price"]),
            quantity=int(result["quantity"]),
            item_emoji=str(item_doc.get("item_emoji") or "🌟"),
        )
        await safe_respond(
            interaction,
            content=(
                f"✅ Paid recorded\n"
                f"User: `{result['user_id']}`\n"
                f"Item: {result['item_name']}\n"
                f"Qty: {result['quantity']}\n"
                f"Income: **{result['income']:,}**"
            ),
            ephemeral=True,
        )
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"Added manual worker income for {person_name(interaction.guild, user)}: "
                f"{result['quantity']:,}x {result['item_name']} "
                f"({result['income']:,} gold)"
            ),
        )

    @app_commands.command(name="spent", description="(Staff) Add manual customer spending")
    @app_commands.autocomplete(user=user_autocomplete, item=item_autocomplete)
    async def spent(
        self,
        interaction: discord.Interaction,
        user: str,
        item: str,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Invalid context.", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Only Bot Developer / Bank Manager.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="spent", seconds=3)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        item_doc = await ItemService(ctx).get_by_id(item)
        if not item_doc:
            await safe_respond(interaction, content="❌ Item not found.", ephemeral=True)
            return

        member = interaction.guild.get_member(int(user)) if user.isdigit() else None
        user_label = member.display_name if member else fallback_user_label(user)
        item_name = item_doc.get("item_name", item)

        confirm_embed = discord.Embed(
            title="Confirm Spent",
            description=(
                "Please review the details below.\n"
                "Click **Confirm** to record customer spending, or **Cancel**."
            ),
            color=0xFFD700,
        )
        confirm_embed.add_field(name="Customer", value=user_label, inline=True)
        confirm_embed.add_field(name="Item", value=item_name, inline=True)
        confirm_embed.add_field(name="Quantity", value=str(quantity), inline=True)

        view = ConfirmView(author_id=interaction.user.id, timeout_seconds=30)
        await safe_respond(interaction, embed=confirm_embed, view=view, ephemeral=True)

        confirmed = await view.wait_result()
        if not confirmed:
            await safe_respond(interaction, content="❌ Spent cancelled.", ephemeral=True)
            return

        try:
            result = await EconomyService(ctx).spent_customer(
                user_id=user,
                item_id=item,
                quantity=quantity,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        schedule_member_tier_sync(interaction.guild, user, ctx)
        await post_transaction_embed(
            guild=interaction.guild,
            ctx=ctx,
            target="customer",
            member=member,
            item_name=str(result["item_name"]),
            item_price=int(result["item_price"]),
            quantity=int(result["quantity"]),
            item_emoji=str(item_doc.get("item_emoji") or "🌟"),
        )
        await safe_respond(
            interaction,
            content=(
                f"✅ Spent recorded\n"
                f"User: `{result['user_id']}`\n"
                f"Item: {result['item_name']}\n"
                f"Qty: {result['quantity']}\n"
                f"Total: **{result['spent']:,}**"
            ),
            ephemeral=True,
        )
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=(
                f"Added manual customer spending for {person_name(interaction.guild, user)}: "
                f"{result['quantity']:,}x {result['item_name']} "
                f"({result['spent']:,} gold)"
            ),
        )
