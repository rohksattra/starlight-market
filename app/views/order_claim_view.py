from __future__ import annotations

import discord

from app.handlers.order_claim import get_order_claim_handler
from app.views.order_quantity_view import QuantityModal
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

    async def claim(self, interaction: discord.Interaction) -> None:
        handler = get_order_claim_handler()

        async def on_submit(inter2: discord.Interaction, qty: int) -> None:
            try:
                await handler.handle_claim_action(inter2, action="claim", quantity=qty)
            except Exception:
                await safe_respond(inter2, content="❌ Failed to claim.", ephemeral=True)

        await interaction.response.send_modal(QuantityModal(on_submit=on_submit))

    async def unclaim(self, interaction: discord.Interaction) -> None:
        handler = get_order_claim_handler()

        async def on_submit(inter2: discord.Interaction, qty: int) -> None:
            try:
                await handler.handle_claim_action(inter2, action="unclaim", quantity=qty)
            except Exception:
                await safe_respond(inter2, content="❌ Failed to unclaim.", ephemeral=True)

        await interaction.response.send_modal(QuantityModal(on_submit=on_submit))

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        try:
            await get_order_claim_handler().handle_claim_refresh(interaction)
            await safe_respond(interaction, content="✅ Refreshed.", ephemeral=True)
        except Exception:
            await safe_respond(interaction, content="❌ Failed to refresh.", ephemeral=True)
