# core/bot.py
from __future__ import annotations

import asyncio
import logging
import signal

import discord
from discord.ext import commands

from core.config import settings
from db.bootstrap import bootstrap_database
from db.mongo import close_mongo

from core.web import start_web_background
from app.services.item_service import ItemService
from app.uis.price_button import PriceRefreshView
from app.uis.leaderboard_button import LeaderboardRefreshView
from app.uis.worker_rating_button import RatingWorkerButton


log = logging.getLogger("core.bot")

start_web_background()


class StarlightBot(commands.Bot):
    async def setup_hook(self) -> None:
        await bootstrap_database()
        await load_cogs(self)
        item_serv = ItemService()
        categories = await item_serv.list_categories()
        for category in categories:
            self.add_view(PriceRefreshView(category=category))
        self.add_view(LeaderboardRefreshView(lb_type="worker", title="🏆 Top 50 Workers"))
        self.add_view(LeaderboardRefreshView(lb_type="customer", title="🏅 Top 50 Customers"))
        self.add_view(LeaderboardRefreshView(lb_type="item", title="🛒 Top 50 Items"))
        self.add_view(RatingWorkerButton())
        guild = discord.Object(id=settings.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        log.info("Setup hook completed.")


async def load_cogs(bot: commands.Bot) -> None:
    extensions = (
        "app.cogs.gateway",
        "app.cogs.order_entry",
        "app.cogs.order_action",
        "app.cogs.order_management",
        "app.cogs.custom_order",
        "app.cogs.price",
        "app.cogs.market_statistic",
        "app.cogs.leaderboard",
        "app.cogs.profile",
        "app.cogs.transaction",
        "app.cogs.worker_rating",
        "app.cogs.item_management",
        "app.cogs.server_management",
        "app.cogs.counting",
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
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.messages = True
    intents.message_content = True
    bot = StarlightBot(command_prefix="!", intents=intents)
    @bot.event
    async def on_ready() -> None:
        if getattr(bot, "_ready_ran", False):
            return
        setattr(bot, "_ready_ran", True)
        if bot.user:
            log.info("Connected as %s (%s)", bot.user, bot.user.id)
        log.info("Bot is fully ready.")
    async def runner() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(bot, s)))
            except NotImplementedError:
                pass
        try:
            await bot.start(settings.DISCORD_TOKEN)
        except asyncio.CancelledError:
            log.info("Bot task cancelled.")
        finally:
            await shutdown(bot)
    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")


if __name__ == "__main__":
    run_bot()
