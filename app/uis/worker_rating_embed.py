# app/uis/worker_rating_embed.py
from __future__ import annotations

import discord


def fmt(value: int) -> str:
    return f"{value:,}"


def format_rating_stars(average: float, *, max_stars: int = 5) -> str:
    if average <= 0:
        return ""
    full = int(average)
    has_half = (average - full) >= 0.5
    stars: list[str] = []
    for i in range(max_stars):
        if i < full:
            stars.append("★")
        elif i == full and has_half:
            stars.append("☆")
            has_half = False
        else:
            stars.append("✩")
    return "".join(stars)


def worker_rating_embed(
    *, worker: discord.Member, customer: discord.Member, item_name: str, item_quantity: int, order_channel: discord.TextChannel, item_emoji: str = "🌟"
) -> tuple[str, discord.Embed]:
    item_fmt = f"{item_emoji} {item_name}"
    qty_fmt = f"🏷 ***{fmt(item_quantity)}x***"

    embed = discord.Embed(
        title="⭐ Rate Worker Performance",
        description=(
            f"***{worker.mention}*** has successfully completed "
            f"{qty_fmt} of ***{item_fmt}*** for your order in "
            f"***{order_channel.mention}***\n\n"
            f"Please take a moment to rate their performance."
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")
    return f"🔔 {customer.mention}", embed


def worker_rating_summary(*, average: float, count: int) -> str:
    if count <= 0:
        return "No ratings yet"
    stars = format_rating_stars(average)
    return (
        f"{stars} ***{average:.2f}***\n"
        f"***{fmt(count)}*** rating(s)"
    )