# utils/interaction_safe.py
from __future__ import annotations

import discord
from discord.errors import NotFound, InteractionResponded
from typing import Any


async def safe_defer(interaction: discord.Interaction, *, ephemeral: bool = False) -> None:
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
    except (NotFound, InteractionResponded):
        return


def _build_kwargs(*,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    ephemeral: bool | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view
    if ephemeral is not None:
        kwargs["ephemeral"] = ephemeral
    return kwargs


async def safe_respond(
    interaction: discord.Interaction,
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
) -> None:
    try:
        kwargs = _build_kwargs(content=content, embed=embed, view=view, ephemeral=ephemeral)
        if not kwargs:
            return
        if interaction.response.is_done():
            await interaction.followup.send(**kwargs)
        else:
            await interaction.response.send_message(**kwargs)
    except (NotFound, InteractionResponded):
        return


async def safe_autocomplete(interaction: discord.Interaction, choices: list[discord.app_commands.Choice]) -> None:
    try:
        if interaction.response.is_done():
            return
        await interaction.response.autocomplete(choices[:25])
    except NotFound:
        return


async def safe_edit_message(
    interaction: discord.Interaction,
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
) -> None:
    try:
        kwargs = _build_kwargs(content=content, embed=embed, view=view)
        if not kwargs:
            return
        if interaction.response.is_done():
            await interaction.edit_original_response(**kwargs)
        else:
            await interaction.response.edit_message(**kwargs)
    except (NotFound, InteractionResponded):
        return
