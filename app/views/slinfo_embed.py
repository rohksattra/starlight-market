from __future__ import annotations

import discord

from app.domains.bot_info import BOT_INTRO, COMMAND_GROUPS, CommandEntry, CommandGroup
from app.views.embed_footer import set_starlight_footer

EMBED_COLOR = 0xFFD700
MAX_DESCRIPTION = 4096
MAX_FIELD_VALUE = 1024
MAX_FIELDS = 25
# Keep under Discord's 6000 total-character hard limit.
MAX_EMBED_CHARS = 5500


def _format_commands(commands: list[CommandEntry]) -> str:
    return "\n".join(f"`{entry['name']}` — {entry['description']}" for entry in commands)


def _embed_char_count(embed: discord.Embed) -> int:
    total = len(embed.title or "") + len(embed.description or "")
    if embed.footer and embed.footer.text:
        total += len(embed.footer.text)
    for field in embed.fields:
        total += len(field.name) + len(field.value)
    return total


def _new_embed(
    *,
    title: str,
    description: str | None = None,
    bot_user: discord.ClientUser | discord.User | None = None,
    with_thumbnail: bool = False,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=EMBED_COLOR,
    )
    if with_thumbnail and bot_user is not None:
        embed.set_thumbnail(url=bot_user.display_avatar.url)
    set_starlight_footer(embed, include_button_notice=False)
    return embed


def _can_add_field(embed: discord.Embed, *, name: str, value: str) -> bool:
    if len(embed.fields) >= MAX_FIELDS:
        return False
    if len(value) > MAX_FIELD_VALUE:
        return False
    projected = _embed_char_count(embed) + len(name) + len(value)
    return projected <= MAX_EMBED_CHARS


def _chunk_command_value(commands: list[CommandEntry]) -> list[str]:
    """Split a command list into field values under Discord's 1024 limit."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for entry in commands:
        line = f"`{entry['name']}` — {entry['description']}"
        extra = len(line) + (1 if current else 0)
        if current and current_len + extra > MAX_FIELD_VALUE:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue
        current.append(line)
        current_len += extra

    if current:
        chunks.append("\n".join(current))
    return chunks


def _add_group_fields(embeds: list[discord.Embed], group: CommandGroup, *, page_title: str) -> None:
    chunks = _chunk_command_value(group["commands"])
    for index, value in enumerate(chunks):
        name = group["title"] if index == 0 else f"{group['title']} (cont.)"
        if not embeds or not _can_add_field(embeds[-1], name=name, value=value):
            embeds.append(_new_embed(title=page_title))
        embeds[-1].add_field(name=name, value=value, inline=False)


def slinfo_embeds(*, bot_user: discord.ClientUser | discord.User | None = None) -> list[discord.Embed]:
    intro = BOT_INTRO if len(BOT_INTRO) <= MAX_DESCRIPTION else BOT_INTRO[: MAX_DESCRIPTION - 1] + "…"
    embeds: list[discord.Embed] = [
        _new_embed(
            title="🌟 Starlight Market — Bot Info",
            description=intro,
            bot_user=bot_user,
            with_thumbnail=True,
        )
    ]

    for group in COMMAND_GROUPS:
        page_title = "🌟 Starlight Market — Commands"
        _add_group_fields(embeds, group, page_title=page_title)

    if len(embeds) > 1:
        total = len(embeds)
        for index, embed in enumerate(embeds, start=1):
            set_starlight_footer(
                embed,
                detail=f"Page {index}/{total}",
                include_button_notice=False,
            )

    return embeds
