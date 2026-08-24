"""Market embeds, buttons, and modals (UI only)."""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Literal, Sequence, cast

import discord

from bot.ui.orders import worker_rating_summary
from bot.ui.shared import ctx_from_interaction, set_starlight_footer
from core.period import (
    PERIODS,
    PERIOD_BUTTON_LABELS,
    StatPeriod,
    parse_period_from_custom_id,
    parse_period_from_text,
    period_label,
)
from core.tenant import GameContext, get_context
from core.time import utc_now
from services.tier_limits import ProfileLimitInfo
from services.tiers import (
    customer_tier_for_spent,
    donor_tier_for_total,
    format_limit_remaining,
    worker_tier_for_income,
)
from utils.discord_safe import safe_defer, safe_edit_message, safe_respond

log = logging.getLogger("bot.ui.market")

PAGE_SIZE = 25
COOLDOWN_SECONDS = 60
MAX_ITEMS = 100

LBType = Literal["worker", "customer", "item", "donor"]


def _period_style(period: StatPeriod, selected: StatPeriod) -> discord.ButtonStyle:
    if period == selected:
        return discord.ButtonStyle.primary
    return discord.ButtonStyle.secondary


def _sync_period_from_interaction(view: Any, interaction: discord.Interaction) -> None:
    data = interaction.data or {}
    custom_id = data.get("custom_id")
    if isinstance(custom_id, str):
        parsed = parse_period_from_custom_id(custom_id)
        if parsed is not None:
            view.period = parsed
            return
    message = interaction.message
    if message is None or not message.embeds:
        view.period = "all"
        return
    embed = message.embeds[0]
    view.period = parse_period_from_text(f"{embed.title or ''}\n{embed.description or ''}")


def _page_from_message(interaction: discord.Interaction) -> int | None:
    message = interaction.message
    if message is None or not message.embeds:
        return None
    footer = message.embeds[0].footer.text or ""
    match = re.search(r"Page\s+(\d+)/(\d+)", footer)
    if not match:
        return None
    return max(0, int(match.group(1)) - 1)


def _period_callback(view: Any, period: StatPeriod):
    async def callback(interaction: discord.Interaction) -> None:
        view.period = period
        await view.on_period_selected(interaction)

    return callback


def _attach_period_buttons(view: Any, *, prefix: str, row: int = 0) -> None:
    view.period = getattr(view, "period", "all")
    view._period_btns = {}
    for key in PERIODS:
        btn = discord.ui.Button(
            label=PERIOD_BUTTON_LABELS[key],
            style=_period_style(key, view.period),
            custom_id=f"{prefix}:p:{key}",
            row=row,
        )
        btn.callback = _period_callback(view, key)
        view._period_btns[key] = btn
        view.add_item(btn)


def _apply_period_styles(view: Any) -> None:
    for key, btn in getattr(view, "_period_btns", {}).items():
        btn.style = _period_style(key, view.period)


def _titled_with_period(title: str, period: StatPeriod) -> str:
    return f"{title} · {period_label(period)}"


def _display_worker_role_id(total_income: int, ctx: GameContext) -> int:
    if total_income <= 0:
        return ctx.roles.worker
    tier_name = worker_tier_for_income(total_income, game=ctx.game)
    if tier_name:
        rid = ctx.roles.worker_tiers.get(tier_name)
        if rid:
            return rid
    return ctx.roles.worker


def _display_customer_role_id(total_spent: int, ctx: GameContext) -> int:
    if total_spent <= 0:
        return ctx.roles.customer
    tier_name = customer_tier_for_spent(total_spent, game=ctx.game)
    if tier_name:
        rid = ctx.roles.customer_tiers.get(tier_name)
        if rid:
            return rid
    return ctx.roles.customer


def _display_donor_role_id(total_donated: int, ctx: GameContext) -> int | None:
    if total_donated <= 0:
        return None
    tier_name = donor_tier_for_total(total_donated, game=ctx.game)
    if not tier_name:
        return None
    return ctx.roles.donor_tiers.get(tier_name)


def _role_mention(guild: discord.Guild | None, role_id: int) -> str:
    if guild is not None:
        role = guild.get_role(role_id)
        if role is not None:
            return role.mention
    return f"<@&{role_id}>"


def _limit_line(*, label: str, remaining: int, maximum: int | None) -> str:
    return f"{label}: ***{format_limit_remaining(remaining=remaining, maximum=maximum)}***"


def profile_embed(
    *,
    member: discord.Member,
    ctx: GameContext,
    worker_orders: List[str],
    customer_orders: List[str],
    worker_rank: int | None,
    customer_rank: int | None,
    donor_rank: int | None,
    total_income: int,
    total_spent: int,
    donation_given: int,
    worker_rating_avg: float = 0.0,
    worker_rating_count: int = 0,
    limits: ProfileLimitInfo | None = None,
) -> discord.Embed:
    color = 0xFFD700
    rating_text = worker_rating_summary(average=worker_rating_avg, count=worker_rating_count)
    worker_rank_text = f"#{worker_rank:,}" if worker_rank is not None else "Not ranked yet"
    customer_rank_text = f"#{customer_rank:,}" if customer_rank is not None else "Not ranked yet"
    donor_rank_text = f"#{donor_rank:,}" if donor_rank is not None else "Not ranked yet"

    income_i = int(total_income)
    spent_i = int(total_spent)
    donation_i = int(donation_given)

    donor_tier_id = _display_donor_role_id(donation_i, ctx)
    donor_tier_line = (
        _role_mention(member.guild, donor_tier_id)
        if donor_tier_id is not None
        else "No tier unlocked yet"
    )
    worker_role_line = _role_mention(member.guild, _display_worker_role_id(income_i, ctx))
    customer_role_line = _role_mention(member.guild, _display_customer_role_id(spent_i, ctx))

    worker_limit_lines = ""
    customer_limit_lines = ""
    donor_limit_lines = ""
    if limits is not None:
        worker_limit_lines = (
            f"{_limit_line(label='Claim Order Remaining', remaining=limits.claim_order_remaining, maximum=limits.claim_order_max)}\n"
            f"{_limit_line(label='Claim Capacity Remaining', remaining=limits.claim_capacity_remaining or 0, maximum=limits.claim_capacity_max)}\n"
        )
        customer_limit_lines = (
            f"{_limit_line(label='Active Order Remaining', remaining=limits.active_order_remaining, maximum=limits.active_order_max)}\n"
            f"{_limit_line(label='Order Capacity Remaining', remaining=limits.order_capacity_remaining or 0, maximum=limits.order_capacity_max)}\n"
        )
        if limits.coupon_max is None:
            donor_limit_lines = "Coupon Remaining: ***Unlimited***\n"
        elif limits.coupon_max > 0:
            donor_limit_lines = (
                f"{_limit_line(label='Coupon Remaining (this month)', remaining=limits.coupon_remaining, maximum=limits.coupon_max)}\n"
            )
        else:
            donor_limit_lines = "Coupon Remaining: ***No donor tier***\n"

    embed = discord.Embed(
        title=f"🪧 {member.display_name}'s Profile",
        color=color,
    )
    embed.description = (
        f"### 💪 As {worker_role_line}\n"
        f"Active Claimed Orders: ***{len(worker_orders)}***\n"
        f"{worker_limit_lines}"
        f"{chr(10).join(worker_orders) if worker_orders else '- No active claimed orders'}\n\n"
        f"Top Worker: 🥇 ***{worker_rank_text}***\n"
        f"Gold Income: 🪙 ***{income_i:,}***\n\n"
        "**⭐ Worker Rating**\n"
        f"{rating_text}\n\n"
        f"### 🛒 As {customer_role_line}\n"
        f"Active Orders Placed: ***{len(customer_orders)}***\n"
        f"{customer_limit_lines}"
        f"{chr(10).join(customer_orders) if customer_orders else '- No active orders'}\n\n"
        f"Top Customer: 🥇 ***{customer_rank_text}***\n"
        f"Gold Spent: 🪙 ***{spent_i:,}***\n\n"
        f"### 🎁 As {donor_tier_line}\n"
        f"{donor_limit_lines}"
        f"Top Donor: 🥇 ***{donor_rank_text}***\n"
        f"Gold Donated: 🪙 ***{donation_i:,}***"
    )
    set_starlight_footer(embed, ctx=ctx, include_button_notice=False)
    return embed


def donation_embed(
    *,
    user_id: str,
    gold: int,
    description: str,
    ctx: GameContext,
    donor_tier_role_id: int | None = None,
) -> discord.Embed:
    raw = (description or "").strip()
    detail_line = discord.utils.escape_markdown(raw.replace("\n", " ")[:900]) if raw else "—"

    tier_block = ""
    if donor_tier_role_id is not None:
        tier_block = (
            f"**Donor tier**\n"
            f"- ***<@&{donor_tier_role_id}>***\n"
        )

    body = (
        f"**Donor**\n"
        f"- ***<@{user_id}>***\n"
        f"**Gold**\n"
        f"- 🪙 ***{gold:,}***\n"
        f"{tier_block}"
        f"**Detail**\n"
        f"- ***{detail_line}***\n\n"
        "*Thank you for your donation.*"
    )

    embed = discord.Embed(
        title="🎁 New Donation",
        description=body,
        color=0xFFD700,
    )
    set_starlight_footer(embed, ctx=ctx, include_button_notice=False)
    return embed


def price_embed(
    *,
    category: str,
    items: List[Dict[str, Any]],
    page: int,
    ctx: GameContext | None = None,
    page_size: int = PAGE_SIZE,
    refreshed_at: datetime | None = None,
) -> discord.Embed:
    start = page * page_size
    end = start + page_size
    sliced = items[start:end]

    lines: List[str] = []
    for item in sliced:
        emoji = item.get("item_emoji") or "🌟"
        name = item.get("item_name", "Unknown Item")
        price = int(item.get("item_price", 0) or 0)
        price_text = "***Unavailable***" if price <= 0 else f"🪙 ***{price:,}***"
        lines.append(f"***{emoji} {name}*** — {price_text}")

    embed = discord.Embed(
        title=f"📦 Price List — ***{category}***",
        description="\n".join(lines) if lines else "⚠️ No items available.",
        color=0xFFD700,
    )

    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    if refreshed_at is None:
        refreshed_at = utc_now()

    set_starlight_footer(
        embed,
        ctx=ctx,
        detail=(
            f"Page {page + 1}/{total_pages} • "
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        ),
    )
    return embed


def claimable_embed(
    *,
    entries: List[Dict[str, Any]],
    page: int,
    page_size: int,
    ctx: GameContext | None = None,
    refreshed_at: datetime | None = None,
) -> discord.Embed:
    start = page * page_size
    end = start + page_size
    sliced = entries[start:end]

    lines = []
    for idx, e in enumerate(sliced, start=start + 1):
        ch = f"<#{e['channel_id']}>" if e.get("channel_id") else "No Channel"
        emoji = e.get("item_emoji") or "🌟"
        name = e.get("item_name", "Unknown")
        qty = int(e.get("value", 0))
        lines.append(f"***{idx}. {emoji} {name} — 🏷 {qty:,}***\n{ch}")

    embed = discord.Embed(
        title="📦 Claimable Orders",
        description="\n".join(lines) if lines else "⚠️ No claimable orders.",
        color=0xFFD700,
    )

    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    if refreshed_at is None:
        refreshed_at = utc_now()

    set_starlight_footer(
        embed,
        ctx=ctx,
        detail=(
            f"Page {page + 1}/{total_pages} • "
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        ),
    )
    return embed


def _fmt_users(guild: discord.Guild, rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return "- No data"

    lines: List[str] = []
    for i, row in enumerate(rows, start=1):
        user_id = row.get("id")
        value = int(row.get("value", 0))
        if not user_id:
            name = "Unknown User"
        else:
            member = guild.get_member(int(user_id))
            name = member.display_name if member else "Unknown"
        lines.append(f"{i}. ***{name}*** — 🪙 ***{value:,}***")
    return "\n".join(lines)


def _fmt_items(rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return "- No data"

    lines: List[str] = []
    for i, row in enumerate(rows, start=1):
        name = row.get("name", "Unknown")
        emoji = row.get("item_emoji") or "🌟"
        value = int(row.get("value", 0))
        lines.append(f"{i}. ***{emoji} {name}*** — 🏷 ***{value:,}x***")
    return "\n".join(lines)


def market_statistic_embed(
    *,
    guild: discord.Guild,
    order: Dict[str, Any],
    gold: Dict[str, Any],
    leaderboard: Dict[str, Sequence[Dict[str, Any]]],
    total_workers: int,
    total_customers: int,
    period: StatPeriod = "all",
    refreshed_at: datetime | None = None,
) -> discord.Embed:
    ctx = get_context(guild.id)
    title = f"📊 {ctx.brand.name} Statistics" if ctx else "📊 Market Statistics"
    period_line = f"**Period:** {period_label(period)}"
    if not order or not gold:
        embed = discord.Embed(
            title=title,
            description=f"{period_line}\n\n⚠️ **No data available.**",
            color=0xFFD700,
        )
        set_starlight_footer(embed, ctx=ctx)
        return embed

    created = int(order.get("created", order.get("total", 0)) or 0)
    rate = float(gold.get("commission_rate", 0.01) or 0)
    avg_size = int(gold.get("avg_order_size", 0) or 0)
    embed = discord.Embed(title=title, color=0xFFD700)
    embed.description = (
        f"{period_line}\n\n"
        "### 🛒 Orders\n"
        f"- Created: 🛒 ***{created:,}***\n"
        f"- Finished: 📦 ***{int(order.get('finished', 0) or 0):,}***\n"
        f"- Canceled: ❌ ***{int(order.get('canceled', 0) or 0):,}***\n"
        f"- Active now: 🔄 ***{int(order.get('active', 0) or 0):,}***\n"
        f"- Ready for pickup: ✅ ***{int(order.get('completed', 0) or 0):,}***\n\n"
        "### 👥 Market\n"
        f"- Workers: 👷 ***{total_workers:,}***\n"
        f"- Customers: 🛍️ ***{total_customers:,}***\n\n"
        "### 🪙 Gold\n"
        f"- Worker income: 🪙 ***{int(gold.get('worker_income', 0) or 0):,}***\n"
        f"- Customer spent: 🪙 ***{int(gold.get('customer_spent', 0) or 0):,}***\n"
        f"- Market commission ({rate * 100:g}%): 🪙 ***{int(gold.get('commission', 0) or 0):,}***\n"
        f"- Items sold: 🏷 ***{int(gold.get('items_sold', 0) or 0):,}***\n"
        f"- Avg. order size: 📊 ***{avg_size:,}***\n\n"
        "### 🥇 Leaderboard\n"
        "**Top 5 Workers**\n"
        f"{_fmt_users(guild, leaderboard.get('workers', []))}\n\n"
        "**Top 5 Customers**\n"
        f"{_fmt_users(guild, leaderboard.get('customers', []))}\n\n"
        "**Top 5 Items**\n"
        f"{_fmt_items(leaderboard.get('items', []))}"
    )

    if refreshed_at is None:
        refreshed_at = utc_now()

    set_starlight_footer(
        embed,
        ctx=ctx,
        detail=(
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        ),
    )
    return embed


def leaderboard_embed(
    *,
    title: str,
    entries: List[Dict[str, Any]],
    lb_type: LBType,
    page: int,
    page_size: int,
    ctx: GameContext | None = None,
    period: StatPeriod = "all",
    refreshed_at: datetime | None = None,
) -> discord.Embed:
    start = page * page_size
    end = start + page_size
    sliced = entries[start:end]

    lines: List[str] = []
    for idx, entry in enumerate(sliced, start=start + 1):
        value = int(entry.get("value", 0))
        if lb_type == "item":
            name = str(entry.get("name", "Unknown Item"))
            emoji = entry.get("item_emoji") or "🌟"
            lines.append(f"***{idx}. {emoji} {name}*** — 🏷 ***{value:,}x***")
        else:
            name = entry.get("name", "Unknown User")
            lines.append(f"***{idx}. {name}*** — 🪙 ***{value:,}***")

    embed = discord.Embed(
        title=_titled_with_period(title, period),
        description="\n".join(lines) if lines else "⚠️ No data available.",
        color=0xFFD700,
    )

    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    if refreshed_at is None:
        refreshed_at = utc_now()

    set_starlight_footer(
        embed,
        ctx=ctx,
        detail=(
            f"Page {page + 1}/{total_pages} • "
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        ),
    )
    return embed


def rated_leaderboard_embed(
    *,
    title: str,
    entries: List[Dict[str, Any]],
    page: int,
    page_size: int,
    ctx: GameContext | None = None,
    period: StatPeriod = "all",
    refreshed_at: datetime | None = None,
) -> discord.Embed:
    start = page * page_size
    end = start + page_size
    sliced = entries[start:end]

    lines: List[str] = []
    for idx, entry in enumerate(sliced, start=start + 1):
        name = entry.get("name", "Unknown User")
        avg = float(entry.get("avg", 0))
        count = int(entry.get("count", 0))
        lines.append(f"***{idx}. {name}*** — ⭐ ***{avg:.2f}*** (*{count:,} rating(s)*)")

    embed = discord.Embed(
        title=_titled_with_period(title, period),
        description="\n".join(lines) if lines else "⚠️ No data available.",
        color=0xFFD700,
    )

    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    if refreshed_at is None:
        refreshed_at = utc_now()

    set_starlight_footer(
        embed,
        ctx=ctx,
        detail=(
            f"Page {page + 1}/{total_pages} • "
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        ),
    )
    return embed
