from __future__ import annotations

import asyncio
import logging
import signal

import discord
from discord.ext import commands

from core.config import settings
from core.view_registry import register_persistent_views
from db.bootstrap import bootstrap_database
from db.mongo import close_mongo
from core.web import start_web_background


log = logging.getLogger("core.bot")


class StarlightBot(commands.Bot):
    async def setup_hook(self) -> None:
        await bootstrap_database()
        await load_cogs(self)
        await register_persistent_views(self)

        if not getattr(self, "_synced", False):
            guild = discord.Object(id=settings.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            self._synced = True

        log.info("Setup hook completed.")


async def load_cogs(bot: commands.Bot) -> None:
    extensions = (
        "app.events.member",
        "app.events.messages",
        "app.cogs.orders.order_entry",
        "app.cogs.orders.order_action",
        "app.cogs.orders.order_management",
        "app.cogs.orders.custom_order",
        "app.cogs.orders.income",
        "app.cogs.orders.manual_income",
        "app.cogs.market.price",
        "app.cogs.market.market_statistic",
        "app.cogs.market.leaderboard",
        "app.cogs.market.claimable",
        "app.cogs.market.profile",
        "app.cogs.market.donation",
        "app.cogs.staff.role_claim",
        "app.cogs.staff.worker_rating",
        "app.cogs.staff.item_management",
        "app.cogs.staff.server_management",
        "app.cogs.community.game",
        "app.cogs.community.giveaway",
    )
    for ext in extensions:
        try:
            await bot.load_extension(ext)
            log.info("Loaded cog: %s", ext)
        except Exception:
            log.exception("Failed to load cog: %s", ext)


async def shutdown(bot: commands.Bot, sig: signal.Signals | None = None) -> None:
    if sig:
        log.warning("Shutdown signal received: %s", sig.name)
    if not bot.is_closed():
        await bot.close()
    await close_mongo()
    log.info("Shutdown completed.")


def run_bot() -> None:
    start_web_background()

    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.messages = True
    intents.message_content = True

    bot = StarlightBot(
        command_prefix="!",
        intents=intents,
    )

    @bot.event
    async def on_ready() -> None:
        if getattr(bot, "_ready_ran", False):
            return
        setattr(bot, "_ready_ran", True)

        if bot.user:
            log.info(
                "Connected as %s (%s)",
                bot.user,
                bot.user.id,
            )

        log.info("Bot is fully ready.")

    async def runner() -> None:
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.create_task(
                        shutdown(bot, s)
                    ),
                )
            except NotImplementedError:
                pass

        try:
            await bot.start(settings.DISCORD_TOKEN)
        except asyncio.CancelledError:
            log.info("Bot task canceled.")
        finally:
            await shutdown(bot)

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")


if __name__ == "__main__":
    run_bot()
