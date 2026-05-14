from __future__ import annotations

from typing import Any, cast

import discord
from discord.ext import commands

from app.uis.order_quantity_view import QuantityModal
from utils.interaction_safe import safe_defer, safe_respond


class OrderClaimView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

        self.claim_btn = discord.ui.Button(
            label="Claim",
            style=discord.ButtonStyle.success,
            custom_id="orderclaim:claim",
        )
        self.unclaim_btn = discord.ui.Button(
            label="Unclaim",
            style=discord.ButtonStyle.danger,
            custom_id="orderclaim:unclaim",
        )
        self.refresh_btn = discord.ui.Button(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            custom_id="orderclaim:refresh",
        )

        self.claim_btn.callback = self.claim
        self.unclaim_btn.callback = self.unclaim
        self.refresh_btn.callback = self.refresh

        self.add_item(self.claim_btn)
        self.add_item(self.unclaim_btn)
        self.add_item(self.refresh_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    def _get_cog(self, interaction: discord.Interaction) -> Any:
        bot = cast(commands.Bot, interaction.client)
        cog = bot.get_cog("OrderActions")
        if cog is None:
            raise RuntimeError("OrderActions cog missing")
        return cog

    async def claim(self, interaction: discord.Interaction) -> None:
        async def on_submit(inter2: discord.Interaction, qty: int) -> None:
            try:
                cog = self._get_cog(inter2)
                await cog.handle_claim_action(inter2, action="claim", quantity=qty)
            except Exception:
                await safe_respond(inter2, content="❌ Failed to claim.", ephemeral=True)

        await interaction.response.send_modal(QuantityModal(on_submit=on_submit))

    async def unclaim(self, interaction: discord.Interaction) -> None:
        async def on_submit(inter2: discord.Interaction, qty: int) -> None:
            try:
                cog = self._get_cog(inter2)
                await cog.handle_claim_action(inter2, action="unclaim", quantity=qty)
            except Exception:
                await safe_respond(inter2, content="❌ Failed to unclaim.", ephemeral=True)

        await interaction.response.send_modal(QuantityModal(on_submit=on_submit))

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        try:
            cog = self._get_cog(interaction)
            await cog.handle_claim_refresh(interaction)
            await safe_respond(interaction, content="✅ Refreshed.", ephemeral=True)
        except Exception:
            await safe_respond(interaction, content="❌ Failed to refresh.", ephemeral=True)

