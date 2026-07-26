from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from app.handlers.order_claim import get_order_claim_handler
from utils.interaction_safe import safe_respond
from utils.cooldown import check_cooldown


class OrderActions(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.handler = get_order_claim_handler()

    async def handle_claim_refresh(self, interaction: discord.Interaction) -> None:
        await self.handler.handle_claim_refresh(interaction)

    async def handle_claim_action(
        self,
        interaction: discord.Interaction,
        *,
        action: Literal["claim", "unclaim"],
        quantity: int,
    ) -> None:
        await self.handler.handle_claim_action(interaction, action=action, quantity=quantity)

    @app_commands.command(name="claim", description="(Worker) Claim items from this order")
    async def claim(self, interaction: discord.Interaction, quantity: int) -> None:
        try:
            check_cooldown(user_id=interaction.user.id, key="claim", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        await self.handle_claim_action(interaction, action="claim", quantity=quantity)

    @app_commands.command(name="unclaim", description="(Worker) Cancel your claim")
    async def unclaim(self, interaction: discord.Interaction, quantity: int) -> None:
        try:
            check_cooldown(user_id=interaction.user.id, key="unclaim", seconds=5)
        except ValueError as exc:
            await safe_respond(interaction, content=f"⏳ {exc}", ephemeral=True)
            return
        await self.handle_claim_action(interaction, action="unclaim", quantity=quantity)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrderActions(bot))
