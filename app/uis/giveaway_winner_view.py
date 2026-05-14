from __future__ import annotations

from typing import List

import discord
from discord import ui


def giveaway_custom_reroll_all(giveaway_id: str) -> str:
    return f"sl_gvw:{giveaway_id}:ra"


def giveaway_custom_reroll_partial(giveaway_id: str) -> str:
    return f"sl_gvw:{giveaway_id}:rp"


def parse_giveaway_winner_custom_id(custom_id: str) -> tuple[str, str] | None:
    parts = custom_id.split(":", 2)
    if len(parts) != 3 or parts[0] != "sl_gvw":
        return None

    gid, action = parts[1], parts[2]
    if action not in ("ra", "rp"):
        return None

    return gid, action


class GiveawayWinnerView(ui.View):
    def __init__(self, giveaway_id: str) -> None:
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

        reroll_all = ui.Button(
            label="Reroll All",
            style=discord.ButtonStyle.danger,
            custom_id=giveaway_custom_reroll_all(giveaway_id),
            row=0,
        )
        reroll_all.callback = self._on_reroll_all
        self.add_item(reroll_all)

        reroll_partial = ui.Button(
            label="Reroll Partial",
            style=discord.ButtonStyle.secondary,
            custom_id=giveaway_custom_reroll_partial(giveaway_id),
            row=0,
        )
        reroll_partial.callback = self._on_reroll_partial
        self.add_item(reroll_partial)

    async def _on_reroll_all(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        await get_giveaway_service().handle_reroll_all(interaction, self.giveaway_id)

    async def _on_reroll_partial(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        await get_giveaway_service().handle_reroll_partial_prompt(interaction, self.giveaway_id)


class GiveawayWinnerSelect(ui.Select):
    def __init__(self, giveaway_id: str, winner_user_ids: List[str], guild: discord.Guild | None) -> None:
        self.giveaway_id = giveaway_id

        options: List[discord.SelectOption] = []
        for i, uid in enumerate(winner_user_ids[:25], start=1):
            label = f"Winner {i}"
            if guild:
                member = guild.get_member(int(uid))
                if member:
                    label = member.display_name[:100]

            options.append(
                discord.SelectOption(
                    label=label,
                    value=uid,
                    description=f"Reroll winner slot #{i}",
                )
            )

        super().__init__(
            placeholder="Choose winner(s) to reroll",
            min_values=1,
            max_values=max(1, len(options)),
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        await get_giveaway_service().handle_reroll_partial_selected(
            interaction,
            self.giveaway_id,
            list(self.values),
        )


class GiveawayWinnerSelectView(ui.View):
    def __init__(self, giveaway_id: str, winner_user_ids: List[str], guild: discord.Guild | None) -> None:
        super().__init__(timeout=120)
        self.add_item(GiveawayWinnerSelect(giveaway_id, winner_user_ids, guild))