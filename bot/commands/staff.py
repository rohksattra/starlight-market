"""Slash & prefix commands for staff tools."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from bot.activity_log import log_activity
from bot.tier_sync import TierRoleService
from bot.ui.staff import RoleClaimView, market_rules_embeds, pickup_guide_embed, role_claim_embed
from core.tenant import get_context
from models.enums import ORDER_MANAGEMENT_ROLES, STAFF_ROLES
from services.items import ItemService
from services.staff import CleanupdataService, DISCORD_BULK_DELETE_LIMIT, validate_delete_quantity
from utils.autocomplete import user_autocomplete
from utils.confirm_view import ConfirmView
from utils.cooldown import check_cooldown
from utils.discord_safe import safe_defer, safe_respond
from utils.permissions import has_any_role
from utils.prefix_feedback import failed, success

log = logging.getLogger("bot.commands.staff")

DISCORD_MESSAGE_MAX_AGE = timedelta(days=14)


class StaffCommands(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def category_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        ctx = get_context(interaction.guild.id)
        if ctx is None:
            return []
        categories = await ItemService(ctx).list_categories()
        query = current.lower()
        return [
            app_commands.Choice(name=c, value=c)
            for c in categories
            if query in c.lower()
        ][:25]

    async def item_by_category_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        ctx = get_context(interaction.guild.id)
        if ctx is None:
            return []
        category = getattr(interaction.namespace, "category", None)
        if not category:
            return []
        items = await ItemService(ctx).list_items_by_category(category)
        query = current.lower()
        return [
            app_commands.Choice(name=i["item_name"], value=i["item_id"])
            for i in items
            if query in str(i["item_name"]).lower()
        ][:25]

    @commands.command(name="mroles")
    async def roles_command(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=8)
            await failed(ctx)
            return

        if not has_any_role(ctx.author, tenant, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Only Bot Developer / Bank Manager.", delete_after=8)
            await failed(ctx)
            return

        channel = ctx.guild.get_channel(tenant.channels.role_claim)
        if not isinstance(channel, discord.TextChannel):
            log.error("role_claim channel invalid | guild=%s", ctx.guild.id)
            await ctx.send("❌ Role claim channel is not configured correctly.", delete_after=8)
            await failed(ctx)
            return

        try:
            await channel.send(embed=role_claim_embed(tenant), view=RoleClaimView())
        except discord.Forbidden:
            await ctx.send("❌ Cannot send messages to the role claim channel.", delete_after=8)
            await failed(ctx)
            return

        await success(ctx)

    @commands.command(name="mrules")
    async def mrules(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=8)
            await failed(ctx)
            return

        if not has_any_role(ctx.author, tenant, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Only Bot Developer / Bank Manager.", delete_after=8)
            await failed(ctx)
            return

        channel = ctx.guild.get_channel(tenant.channels.rules)
        if not isinstance(channel, discord.TextChannel):
            log.error("rules channel invalid | guild=%s", ctx.guild.id)
            await ctx.send("❌ Rules channel is not configured correctly.", delete_after=8)
            await failed(ctx)
            return

        try:
            await channel.send(
                embeds=market_rules_embeds(tenant),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            await ctx.send("❌ Cannot send messages to the rules channel.", delete_after=8)
            await failed(ctx)
            return
        except discord.HTTPException:
            log.exception("Failed to post market rules | guild=%s", ctx.guild.id)
            await ctx.send("❌ Failed to post market rules.", delete_after=8)
            await failed(ctx)
            return

        await success(ctx)

    @commands.command(name="mpickup")
    async def mpickup(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=8)
            await failed(ctx)
            return

        if not has_any_role(ctx.author, tenant, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Only Bot Developer / Bank Manager.", delete_after=8)
            await failed(ctx)
            return

        channel = ctx.guild.get_channel(tenant.channels.pickup)
        if not isinstance(channel, discord.TextChannel):
            log.error("pickup channel invalid | guild=%s", ctx.guild.id)
            await ctx.send("❌ Pickup channel is not configured correctly.", delete_after=8)
            await failed(ctx)
            return

        try:
            await channel.send(
                embed=pickup_guide_embed(tenant),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            await ctx.send("❌ Cannot send messages to the pickup channel.", delete_after=8)
            await failed(ctx)
            return
        except discord.HTTPException:
            log.exception("Failed to post pickup guide | guild=%s", ctx.guild.id)
            await ctx.send("❌ Failed to post pickup guide.", delete_after=8)
            await failed(ctx)
            return

        await success(ctx)

    @app_commands.command(name="update-category-name", description="(Staff) Update category name")
    @app_commands.describe(category="Current category", new_category_name="New category name")
    @app_commands.autocomplete(category=category_autocomplete)
    async def update_category_name(
        self,
        interaction: discord.Interaction,
        category: str,
        new_category_name: str,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Guild only command.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="update_category", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        try:
            await ItemService(ctx).update_category_name(
                old_name=category,
                new_name=new_category_name,
            )
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await safe_respond(
            interaction,
            content=f"✅ Category **{category}** renamed to **{new_category_name.strip()}**.",
            ephemeral=True,
        )
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=f'Renamed category "{category}" to "{new_category_name.strip()}"',
        )

    @app_commands.command(name="update-item-name", description="(Staff) Update item name")
    @app_commands.describe(
        category="Item category",
        item_id="Item to rename",
        new_name="New item name",
    )
    @app_commands.autocomplete(category=category_autocomplete, item_id=item_by_category_autocomplete)
    async def update_item_name(
        self,
        interaction: discord.Interaction,
        category: str,
        item_id: str,
        new_name: str,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Guild only command.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="update_item_name", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        item = await ItemService(ctx).get_by_id(item_id)
        old_name = str((item or {}).get("item_name") or "item")
        try:
            await ItemService(ctx).update_item_name(item_id=item_id, new_name=new_name)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await safe_respond(interaction, content="✅ Item name updated.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=f'Renamed item "{old_name}" to "{new_name.strip()}"',
        )

    @app_commands.command(name="update-item-price", description="(Staff) Update item price")
    @app_commands.describe(
        category="Item category",
        item_id="Item to update",
        new_price="New price (must be > 0)",
    )
    @app_commands.autocomplete(category=category_autocomplete, item_id=item_by_category_autocomplete)
    async def update_item_price(
        self,
        interaction: discord.Interaction,
        category: str,
        item_id: str,
        new_price: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Guild only command.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="update_item_price", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Staff only.", ephemeral=True)
            return

        item = await ItemService(ctx).get_by_id(item_id)
        item_name = str((item or {}).get("item_name") or "item")
        try:
            await ItemService(ctx).update_item_price(item_id=item_id, new_price=new_price)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        await safe_respond(interaction, content="✅ Item price updated.", ephemeral=True)
        await log_activity(
            guild=interaction.guild,
            ctx=ctx,
            member=interaction.user,
            action=f'Updated "{item_name}" price to {new_price:,} gold',
        )

    @commands.command(name="mcleanupdata")
    async def cleanupdata(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        try:
            check_cooldown(user_id=ctx.author.id, key="cleanupdata", seconds=30)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            return

        tenant = get_context(ctx.guild.id)
        if tenant is None:
            await ctx.send("❌ Unknown game server.", delete_after=5)
            await failed(ctx)
            return

        if not has_any_role(ctx.author, tenant, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Staff only.", delete_after=5)
            await failed(ctx)
            return

        await success(ctx)

        view = ConfirmView(author_id=ctx.author.id, timeout_seconds=30)
        confirm_msg = await ctx.send(
            "⚠️ **Confirmation Required**\n\n"
            "This will permanently delete:\n"
            "- Orders (closed / canceled) > **365 days (1 year)**\n"
            "- Transactions > **365 days (1 year)**\n"
            "- Worker ratings > **365 days (1 year)**\n\n"
            "Click **Confirm** to proceed, or **Cancel**.",
            view=view,
        )
        confirmed = await view.wait_result()
        try:
            await confirm_msg.edit(view=view)
        except discord.HTTPException:
            pass

        if not confirmed:
            await ctx.send("❌ Cleanup cancelled.", delete_after=5)
            await confirm_msg.delete(delay=5)
            return

        try:
            result = await CleanupdataService(tenant).cleanupdata()
        except Exception:
            log.exception("Cleanupdata failed | game=%s", tenant.game)
            await ctx.send("❌ Cleanup failed. Check logs.", delete_after=5)
            await confirm_msg.delete(delay=5)
            return

        result_msg = await ctx.send(
            "🧹 **Cleanup Completed**\n"
            f"📦 Orders: {result['orders_deleted']} | "
            f"💰 Transactions: {result['transactions_deleted']} | "
            f"⭐ Ratings: {result['ratings_deleted']}"
        )
        await log_activity(
            guild=ctx.guild,
            ctx=tenant,
            member=ctx.author,
            action=(
                "Ran data cleanup "
                f"(orders: {result['orders_deleted']}, "
                f"transactions: {result['transactions_deleted']}, "
                f"ratings: {result['ratings_deleted']})"
            ),
            status="warning",
        )
        await result_msg.delete(delay=10)
        await confirm_msg.delete(delay=5)

    @app_commands.command(
        name="delete-message",
        description="(Staff) Delete recent messages from this channel",
    )
    @app_commands.describe(quantity=f"Number of messages to delete (max {DISCORD_BULK_DELETE_LIMIT})")
    async def delete_message(
        self,
        interaction: discord.Interaction,
        quantity: int,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Guild only command.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Text channel only.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="delete_message", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, STAFF_ROLES):
            await safe_respond(
                interaction,
                content="❌ You don't have permission to use this command.",
                ephemeral=True,
            )
            return

        try:
            validate_delete_quantity(quantity)
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return

        min_time = datetime.now(timezone.utc) - DISCORD_MESSAGE_MAX_AGE
        messages: list[discord.Message] = []
        try:
            async for msg in interaction.channel.history(limit=quantity):
                if msg.pinned or msg.created_at < min_time:
                    continue
                messages.append(msg)
        except discord.Forbidden:
            await safe_respond(interaction, content="❌ Missing permission.", ephemeral=True)
            return
        except discord.HTTPException:
            await safe_respond(interaction, content="❌ Discord API error.", ephemeral=True)
            return

        if not messages:
            await safe_respond(
                interaction,
                content="❌ No messages can be deleted (older than 14 days or pinned).",
                ephemeral=True,
            )
            return

        try:
            await interaction.channel.delete_messages(messages)
        except discord.Forbidden:
            await safe_respond(interaction, content="❌ Missing permission.", ephemeral=True)
            return
        except discord.HTTPException:
            await safe_respond(interaction, content="❌ Discord API error.", ephemeral=True)
            return

        log.info(
            "Messages deleted | channel=%s count=%s by=%s",
            interaction.channel.id,
            len(messages),
            interaction.user.id,
        )
        await safe_respond(
            interaction,
            content=f"🧹 Deleted **{len(messages)}** message(s).",
            ephemeral=True,
        )

    @app_commands.command(
        name="update-member-role",
        description="(Staff) Resync donor, worker, and customer tier roles for selected member",
    )
    @app_commands.describe(user_id="Select member from database")
    @app_commands.autocomplete(user_id=user_autocomplete)
    async def update_member_role(
        self,
        interaction: discord.Interaction,
        user_id: str,
    ) -> None:
        await safe_defer(interaction, ephemeral=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Guild only command.", ephemeral=True)
            return

        try:
            check_cooldown(user_id=interaction.user.id, key="update_member_role", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        ctx = get_context(interaction.guild.id)
        if ctx is None:
            await safe_respond(interaction, content="❌ Unknown game server.", ephemeral=True)
            return

        if not has_any_role(interaction.user, ctx, ORDER_MANAGEMENT_ROLES):
            await safe_respond(
                interaction,
                content="❌ Only Bot Developer / Bank Manager.",
                ephemeral=True,
            )
            return

        if not user_id.isdigit():
            await safe_respond(interaction, content="❌ Invalid user ID.", ephemeral=True)
            return

        try:
            member = interaction.guild.get_member(int(user_id))
            if member is None:
                member = await interaction.guild.fetch_member(int(user_id))
        except discord.NotFound:
            await safe_respond(
                interaction,
                content="❌ Member not found in this server.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await safe_respond(
                interaction,
                content="❌ Failed to fetch member. Try again in a moment.",
                ephemeral=True,
            )
            return

        try:
            await TierRoleService(ctx).sync_member(member)
        except Exception:
            log.exception("update-member-role failed | user=%s", user_id)
            await safe_respond(
                interaction,
                content="❌ Tier resync failed. Check logs.",
                ephemeral=True,
            )
            return

        await safe_respond(
            interaction,
            content=f"✅ Tier role synced for {member.mention}.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StaffCommands(bot))
