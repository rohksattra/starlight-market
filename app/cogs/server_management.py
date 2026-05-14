from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.role_map import has_any_role
from app.domains.enums.role_enum import ORDER_MANAGEMENT_ROLES
from app.services.cleanupdata_service import CleanupdataService
from app.services.server_service import ServerService
from app.services.tier_role_service import TierRoleService
from utils.interaction_safe import safe_defer, safe_respond
from utils.cooldown import check_cooldown

log = logging.getLogger("cogs.server_management")


class ServerManagement(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.clean_up_data_serv = CleanupdataService()
        self.server_serv = ServerService()
        self.tier_roles = TierRoleService()

    @commands.command(name="cleanupdata")
    async def cleanupdata(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member):
            return
        try:
            check_cooldown(user_id=ctx.author.id, key="cleanupdata", seconds=30)
        except ValueError as exc:
            await ctx.send(f"⏳ {exc}", delete_after=5)
            return
        if not has_any_role(ctx.author, ORDER_MANAGEMENT_ROLES):
            await ctx.send("❌ Staff only.", delete_after=5)
            return
        try:
            await ctx.message.add_reaction("✅")
        except discord.Forbidden:
            pass
        await ctx.message.delete(delay=5)
        confirm_msg = await ctx.send(
            "⚠️ **Confirmation Required**\n\n"
            "This will permanently delete:\n"
            "- Orders (closed / canceled) > **90 days**\n"
            "- Transactions > **90 days**\n"
            "- Worker ratings > **90 days**\n\n"
            "Reply with **Yes** or **No**."
            )
        
        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel
        try:
            reply = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            await confirm_msg.edit(content="⏱️ Cleanup confirmation timed out.")
            await confirm_msg.delete(delay=5)
            return
        if reply.content.lower() not in {"yes", "y"}:
            try:
                await reply.add_reaction("✅")
            except discord.Forbidden:
                pass
            await reply.delete(delay=5)
            await confirm_msg.delete(delay=5)
            return
        try:
            await reply.add_reaction("✅")
        except discord.Forbidden:
            pass
        await reply.delete(delay=5)
        try:
            result = await self.clean_up_data_serv.cleanupdata()
        except Exception:
            await ctx.send("❌ Cleanup failed. Check logs.", delete_after=5)
            return
        result_msg = await ctx.send(
            "🧹 **Cleanup Completed**\n"
            f"📦 Orders: {result['orders_deleted']} | "
            f"💰 Transactions: {result['transactions_deleted']} | "
            f"⭐ Ratings: {result['ratings_deleted']}"
        )
        await result_msg.delete(delay=10)
        await confirm_msg.delete(delay=5)

    
    @app_commands.command(name="delete-message", description="(Staff) Delete recent messages from this channel")
    @app_commands.describe(quantity="Number of messages to delete (max 100)")
    async def delete_message(self, interaction: discord.Interaction, quantity: int) -> None:
        await safe_defer(interaction, ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
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
        try:
            self.server_serv.ensure_allowed(interaction.user)
            deleted = await self.server_serv.delete_messages(channel=interaction.channel, quantity=quantity)
        except PermissionError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        except ValueError as exc:
            await safe_respond(interaction, content=f"❌ {exc}", ephemeral=True)
            return
        except discord.Forbidden:
            await safe_respond(interaction, content="❌ Missing permission.", ephemeral=True)
            return
        except discord.HTTPException:
            await safe_respond(interaction, content="❌ Discord API error.", ephemeral=True)
            return
        await safe_respond(interaction, content=f"🧹 Deleted **{deleted}** message(s).", ephemeral=True)

    @app_commands.command(
        name="update-member-role",
        description="(Staff) Resync donor, worker, and customer tier roles for all members from database",
    )
    async def update_member_role(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await safe_respond(interaction, content="❌ Guild only command.", ephemeral=True)
            return
        if not has_any_role(interaction.user, ORDER_MANAGEMENT_ROLES):
            await safe_respond(interaction, content="❌ Only Bot Developer / Bank Manager.", ephemeral=True)
            return
        try:
            check_cooldown(user_id=interaction.user.id, key="update_member_role", seconds=10)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return

        try:
            stats = await self.tier_roles.bulk_sync_guild(interaction.guild)
        except discord.HTTPException:
            await safe_respond(
                interaction,
                content="❌ Failed while loading members. Try again in a moment.",
                ephemeral=True,
            )
            return
        except Exception:
            log.exception("update-member-role bulk sync failed")
            await safe_respond(interaction, content="❌ Tier resync failed. Check logs.", ephemeral=True)
            return

        err = int(stats.get("errors", 0))
        n = int(stats.get("members", 0))
        msg = (
            f"✅ Tier role resync finished.\n"
            f"Members processed: **{n:,}**"
        )
        if err:
            msg += f"\n⚠️ **{err}** member(s) hit errors (missing permissions or API issues — see logs)."
        await safe_respond(interaction, content=msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerManagement(bot))
