"""Bot entrypoint, extension loading, and shutdown."""
from __future__ import annotations

import asyncio
import logging
import signal

import discord
from discord.ext import commands

from core.settings import settings
from core.startup import bootstrap
from core.tenant import all_contexts, load_all_tenants
from core.view_registry import register_persistent_views
from core.web import start_web_background
from database.connection import close_mongo
from utils.logger import setup_logging

log = logging.getLogger("core.bot")

EXTENSIONS: tuple[str, ...] = (
    "bot.events.members",
    "bot.events.messages",
    "bot.events.activity",
    "bot.commands.orders",
    "bot.commands.market",
    "bot.commands.staff",
    "bot.commands.community",
)


class StarlightBot(commands.Bot):
    async def setup_hook(self) -> None:
        load_all_tenants()
        await bootstrap()
        await register_persistent_views(self)

        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                log.info("Extension loaded: %s", ext)
            except Exception:
                log.exception("Failed to load extension: %s", ext)

        if not getattr(self, "_synced", False):
            for ctx in all_contexts():
                guild = discord.Object(id=ctx.guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info("Slash commands synced | guild=%s game=%s", ctx.guild_id, ctx.game)
            self._synced = True


async def shutdown(bot: commands.Bot, sig: signal.Signals | None = None) -> None:
    if sig:
        log.warning("Shutdown signal received: %s", sig.name)
    if not bot.is_closed():
        await bot.close()
    await close_mongo()
    log.info("Shutdown complete")


def run_bot() -> None:
    setup_logging()

    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.messages = True
    intents.message_content = True

    bot = StarlightBot(command_prefix="!", intents=intents)
    start_web_background(bot)

    @bot.event
    async def on_ready() -> None:
        if getattr(bot, "_ready_ran", False):
            return
        bot._ready_ran = True  # type: ignore[attr-defined]
        if bot.user:
            log.info("Connected as %s (%s)", bot.user, bot.user.id)
        log.info("Bot is fully ready | tenants=%d", len(all_contexts()))

    async def runner() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.create_task(shutdown(bot, s)),
                )
            except NotImplementedError:
                pass

        try:
            await bot.start(settings.DISCORD_TOKEN)
        except asyncio.CancelledError:
            log.info("Bot task canceled")
        finally:
            await shutdown(bot)

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        log.info("Bot stopped by user")
