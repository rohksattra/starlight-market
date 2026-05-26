from __future__ import annotations

import logging

import discord
from discord import ui


log = logging.getLogger("uis.giveaway_view")


def giveaway_custom_join(giveaway_id: str) -> str:
    return f"sl_gv:{giveaway_id}:j"


def giveaway_custom_participants(giveaway_id: str) -> str:
    return f"sl_gv:{giveaway_id}:p"


def giveaway_custom_refresh(giveaway_id: str) -> str:
    return f"sl_gv:{giveaway_id}:r"


def giveaway_custom_cancel(giveaway_id: str) -> str:
    return f"sl_gv:{giveaway_id}:c"


def parse_giveaway_custom_id(custom_id: str) -> tuple[str, str] | None:
    parts = custom_id.split(":", 2)

    if len(parts) != 3 or parts[0] != "sl_gv":
        return None

    gid, action = parts[1], parts[2]

    if action not in ("j", "p", "r", "c"):
        return None

    return gid, action


class GiveawayView(ui.View):
    def __init__(
        self,
        giveaway_id: str,
        *,
        join_disabled: bool = False,
        refresh_disabled: bool = False,
        cancel_disabled: bool = False,
    ) -> None:
        super().__init__(timeout=None)

        self.giveaway_id = giveaway_id

        join_btn = ui.Button(
            label="Join",
            style=discord.ButtonStyle.success,
            custom_id=giveaway_custom_join(giveaway_id),
            disabled=join_disabled,
            row=0,
        )
        join_btn.callback = self._on_join
        self.add_item(join_btn)

        part_btn = ui.Button(
            label="Participants",
            style=discord.ButtonStyle.primary,
            custom_id=giveaway_custom_participants(giveaway_id),
            row=0,
        )
        part_btn.callback = self._on_participants
        self.add_item(part_btn)

        ref_btn = ui.Button(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            custom_id=giveaway_custom_refresh(giveaway_id),
            disabled=refresh_disabled,
            row=0,
        )
        ref_btn.callback = self._on_refresh
        self.add_item(ref_btn)

        cancel_btn = ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            custom_id=giveaway_custom_cancel(giveaway_id),
            disabled=cancel_disabled,
            row=0,
        )
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    def refresh_buttons(
        self,
        *,
        join_disabled: bool,
        refresh_disabled: bool,
        cancel_disabled: bool,
    ) -> None:
        for child in self.children:
            if not isinstance(child, ui.Button):
                continue

            if child.custom_id == giveaway_custom_join(self.giveaway_id):
                child.disabled = join_disabled

            elif child.custom_id == giveaway_custom_refresh(self.giveaway_id):
                child.disabled = refresh_disabled

            elif child.custom_id == giveaway_custom_cancel(self.giveaway_id):
                child.disabled = cancel_disabled

    async def _on_join(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        await get_giveaway_service().handle_join(
            interaction,
            self.giveaway_id,
        )

    async def _on_participants(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        await get_giveaway_service().handle_participants(
            interaction,
            self.giveaway_id,
        )

    async def _on_refresh(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        await get_giveaway_service().handle_refresh(
            interaction,
            self.giveaway_id,
        )

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        from app.services.giveaway_service import get_giveaway_service

        await get_giveaway_service().handle_cancel_giveaway(
            interaction,
            self.giveaway_id,
        )