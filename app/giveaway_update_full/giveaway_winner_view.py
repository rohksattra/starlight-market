from __future__ import annotations

from typing import List, Literal

import discord
from discord import ui


WinnerSelectMode = Literal["reroll", "claim"]


def giveaway_custom_reroll_all(giveaway_id: str) -> str:
    return f"sl_gvw:{giveaway_id}:ra"


def giveaway_custom_reroll_partial(giveaway_id: str) -> str:
    return f"sl_gvw:{giveaway_id}:rp"


def giveaway_custom_claim(giveaway_id: str) -> str:
    return f"sl_gvw:{giveaway_id}:cl"


def giveaway_custom_close(giveaway_id: str) -> str:
    return f"sl_gvw:{giveaway_id}:x"


def parse_giveaway_winner_custom_id(custom_id: str) -> tuple[str, str] | None:
    parts = custom_id.split(":", 2)

    if len(parts) != 3 or parts[0] != "sl_gvw":
        return None

    gid, action = parts[1], parts[2]

    if action not in ("ra", "rp", "cl", "x"):
        return None

    return gid, action


class GiveawayWinnerView(ui.View):
    def __init__(
        self,
        giveaway_id: str,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(timeout=None)

        self.giveaway_id = giveaway_id

        reroll_all = ui.Button(
            label="Reroll All",
            style=discord.ButtonStyle.danger,
            custom_id=giveaway_custom_reroll_all(giveaway_id),
            disabled=disabled,
            row=0,
        )
        reroll_all.callback = self._on_reroll_all
        self.add_item(reroll_all)

        reroll_partial = ui.Button(
            label="Reroll Partial",
            style=discord.ButtonStyle.secondary,
            custom_id=giveaway_custom_reroll_partial(giveaway_id),
            disabled=disabled,
            row=0,
        )
        reroll_partial.callback = self._on_reroll_partial
        self.add_item(reroll_partial)

        claim_btn = ui.Button(
            label="Mark Claimed",
            style=discord.ButtonStyle.success,
            custom_id=giveaway_custom_claim(giveaway_id),
            disabled=disabled,
            row=1,
        )
        claim_btn.callback = self._on_claim
        self.add_item(claim_btn)

        close_btn = ui.Button(
            label="Close Giveaway",
            style=discord.ButtonStyle.primary,
            custom_id=giveaway_custom_close(giveaway_id),
            disabled=disabled,
            row=1,
        )
        close_btn.callback = self._on_close
        self.add_item(close_btn)

    async def _on_reroll_all(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        await get_giveaway_service().handle_reroll_all(
            interaction,
            self.giveaway_id,
        )

    async def _on_reroll_partial(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        await get_giveaway_service().handle_reroll_partial_prompt(
            interaction,
            self.giveaway_id,
        )

    async def _on_claim(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        await get_giveaway_service().handle_mark_claimed_prompt(
            interaction,
            self.giveaway_id,
        )

    async def _on_close(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        await get_giveaway_service().handle_close_giveaway(
            interaction,
            self.giveaway_id,
        )


class GiveawayWinnerSelect(ui.Select):
    def __init__(
        self,
        giveaway_id: str,
        winner_user_ids: List[str],
        guild: discord.Guild | None,
        *,
        mode: WinnerSelectMode,
    ) -> None:
        self.giveaway_id = giveaway_id
        self.mode = mode

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
                    description=f"Winner slot #{i}",
                )
            )

        super().__init__(
            placeholder="Choose winner(s)",
            min_values=1,
            max_values=max(1, len(options)),
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        service = get_giveaway_service()

        if self.mode == "claim":
            await service.handle_mark_claimed_selected(
                interaction,
                self.giveaway_id,
                list(self.values),
            )
            return

        await service.handle_reroll_partial_selected(
            interaction,
            self.giveaway_id,
            list(self.values),
        )


class GiveawayWinnerSelectView(ui.View):
    def __init__(
        self,
        giveaway_id: str,
        winner_user_ids: List[str],
        guild: discord.Guild | None,
        *,
        mode: WinnerSelectMode,
    ) -> None:
        super().__init__(timeout=120)

        self.add_item(
            GiveawayWinnerSelect(
                giveaway_id,
                winner_user_ids,
                guild,
                mode=mode,
            )
        )
