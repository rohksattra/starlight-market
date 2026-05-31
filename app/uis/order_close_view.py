from __future__ import annotations

import logging
from typing import Any, cast

import discord
from discord.ext import commands

from utils.interaction_safe import safe_defer, safe_respond


log = logging.getLogger("uis.order_close_view")

CLOSE_ORDER_CUSTOM_ID = "orderclose:close"
CONFIRM_TIMEOUT_SECONDS = 30


class OrderCloseConfirmView(discord.ui.View):
    def __init__(self, *, cog: Any) -> None:
        super().__init__(timeout=CONFIRM_TIMEOUT_SECONDS)
        self.cog = cog
        self.message: discord.Message | None = None

        yes_btn = discord.ui.Button(
            label="Yes",
            style=discord.ButtonStyle.success,
        )
        no_btn = discord.ui.Button(
            label="No",
            style=discord.ButtonStyle.secondary,
        )
        yes_btn.callback = self._yes
        no_btn.callback = self._no
        self.add_item(yes_btn)
        self.add_item(no_btn)

    async def _delete_message(self) -> None:
        if self.message is None:
            return
        try:
            await self.message.delete()
        except discord.HTTPException:
            log.debug("Failed to delete close confirmation message")

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        await self._delete_message()

    async def _yes(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Invalid channel.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        self.stop()

        await safe_defer(interaction, ephemeral=True)
        await self._delete_message()

        try:
            await self.cog.finalize_close_order(interaction, channel=interaction.channel)
        except Exception:
            log.exception("Failed to finalize order close")
            await safe_respond(
                interaction,
                content="❌ Failed to close order.",
                ephemeral=True,
            )

    async def _no(self, interaction: discord.Interaction) -> None:
        for child in self.children:
            child.disabled = True
        self.stop()
        await safe_defer(interaction, ephemeral=True)
        await self._delete_message()
        await safe_respond(interaction, content="❌ Order close cancelled.", ephemeral=True)


class OrderCloseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        btn = discord.ui.Button(
            label="Close Order",
            style=discord.ButtonStyle.danger,
            custom_id=CLOSE_ORDER_CUSTOM_ID,
        )
        btn.callback = self.close_order
        self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    def _order_management_cog(self, interaction: discord.Interaction) -> Any:
        bot = cast(commands.Bot, interaction.client)
        cog = bot.get_cog("OrderManagement")
        if cog is None:
            raise RuntimeError("OrderManagement cog missing")
        return cog

    async def close_order(self, interaction: discord.Interaction) -> None:
        cog = self._order_management_cog(interaction)
        await cog.handle_close_order_button(interaction)
