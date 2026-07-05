from __future__ import annotations

import discord


STARLIGHT_BRAND = "🌟 Starlight Market"

BUTTON_PRESS_NOTICE = (
    "💡 Bot may sometimes be a bit slow due to its hosting location. "
    "Please don't press the button too many times — just press once and wait."
)


def starlight_footer_text(*, detail: str | None = None, include_button_notice: bool = True) -> str:
    head = STARLIGHT_BRAND if not detail else f"{STARLIGHT_BRAND} • {detail}"
    if not include_button_notice:
        return head
    return f"{head}\n{BUTTON_PRESS_NOTICE}"


def set_starlight_footer(
    embed: discord.Embed,
    *,
    detail: str | None = None,
    include_button_notice: bool = True,
) -> discord.Embed:
    embed.set_footer(
        text=starlight_footer_text(
            detail=detail,
            include_button_notice=include_button_notice,
        )
    )
    return embed


def button_notice_content_suffix() -> str:
    return f"\n\n{BUTTON_PRESS_NOTICE}"
