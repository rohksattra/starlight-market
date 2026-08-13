"""Market embeds, buttons, and modals (UI only)."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Literal, Sequence, cast

import discord

from bot.ui.orders import worker_rating_summary
from bot.ui.shared import set_starlight_footer
from core.tenant import GameContext, get_context
from services.tier_limits import ProfileLimitInfo
from services.tiers import (
    customer_tier_for_spent,
    donor_tier_for_total,
    format_limit_remaining,
    worker_tier_for_income,
)
from utils.discord_safe import safe_defer, safe_edit_message, safe_respond

PAGE_SIZE = 25
COOLDOWN_SECONDS = 60
MAX_ITEMS = 100

LBType = Literal["worker", "customer", "item", "donor"]


def _display_worker_role_id(total_income: int, ctx: GameContext) -> int:
    if total_income <= 0:
        return ctx.roles.worker
    tier_name = worker_tier_for_income(total_income)
    if tier_name:
        rid = ctx.roles.worker_tiers.get(tier_name)
        if rid:
            return rid
    return ctx.roles.worker


def _display_customer_role_id(total_spent: int, ctx: GameContext) -> int:
    if total_spent <= 0:
        return ctx.roles.customer
    tier_name = customer_tier_for_spent(total_spent)
    if tier_name:
        rid = ctx.roles.customer_tiers.get(tier_name)
        if rid:
            return rid
    return ctx.roles.customer


def _display_donor_role_id(total_donated: int, ctx: GameContext) -> int | None:
    if total_donated <= 0:
        return None
    tier_name = donor_tier_for_total(total_donated)
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
        if limits.coupon_max > 0:
            donor_limit_lines = (
                f"{_limit_line(label='Coupon Remaining', remaining=limits.coupon_remaining, maximum=limits.coupon_max)}\n"
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
    set_starlight_footer(embed, include_button_notice=False)
    return embed


def donation_embed(
    *,
    user_id: str,
    gold: int,
    description: str,
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
    set_starlight_footer(embed, include_button_notice=False)
    return embed


def price_embed(
    *,
    category: str,
    items: List[Dict[str, Any]],
    page: int,
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
        refreshed_at = datetime.utcnow()

    set_starlight_footer(
        embed,
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
        refreshed_at = datetime.utcnow()

    set_starlight_footer(
        embed,
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
    order: Dict[str, int],
    gold: Dict[str, int],
    leaderboard: Dict[str, Sequence[Dict[str, Any]]],
    total_workers: int,
    total_customers: int,
    refreshed_at: datetime | None = None,
) -> discord.Embed:
    if not order or not gold:
        embed = discord.Embed(
            title="📊 Starlight Market Statistics",
            description="⚠️ **No data available.**",
            color=0xFFD700,
        )
        set_starlight_footer(embed)
        return embed

    completed = order.get("completed", 0)
    embed = discord.Embed(title="📊 Starlight Market Statistics", color=0xFFD700)
    embed.description = (
        "### 🛒 Order Overview\n"
        f"- Total Orders: 🛒 ***{order.get('total', 0):,}***\n"
        f"- Active Orders: 🔄 ***{order.get('active', 0):,}***\n"
        f"- Completed Orders: ✅ ***{completed:,}***\n"
        f"- Finished Orders: 📦 ***{order.get('finished', 0):,}***\n"
        f"- Canceled Orders: ❌ ***{order.get('canceled', 0):,}***\n\n"
        "### 👥 Market Overview\n"
        f"- Total Workers: 👷 ***{total_workers:,}***\n"
        f"- Total Customers: 🛍️ ***{total_customers:,}***\n\n"
        "### 🪙 Gold Overview\n"
        f"- Workers Income: 🪙 ***{gold.get('worker_income', 0):,}***\n"
        f"- Customers Spent: 🪙 ***{gold.get('customer_spent', 0):,}***\n\n"
        "### 🥇 Leaderboard\n"
        "**Top 5 Workers**\n"
        f"{_fmt_users(guild, leaderboard.get('workers', []))}\n\n"
        "**Top 5 Customers**\n"
        f"{_fmt_users(guild, leaderboard.get('customers', []))}\n\n"
        "**Top 5 Items**\n"
        f"{_fmt_items(leaderboard.get('items', []))}"
    )

    if refreshed_at is None:
        refreshed_at = datetime.utcnow()

    set_starlight_footer(
        embed,
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
        title=title,
        description="\n".join(lines) if lines else "⚠️ No data available.",
        color=0xFFD700,
    )

    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    if refreshed_at is None:
        refreshed_at = datetime.utcnow()

    set_starlight_footer(
        embed,
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
        title=title,
        description="\n".join(lines) if lines else "⚠️ No data available.",
        color=0xFFD700,
    )

    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    if refreshed_at is None:
        refreshed_at = datetime.utcnow()

    set_starlight_footer(
        embed,
        detail=(
            f"Page {page + 1}/{total_pages} • "
            f"Last refresh: {refreshed_at:%b %d, %Y} "
            f"at {refreshed_at:%H:%M UTC}"
        ),
    )
    return embed


class PricePaginationView(discord.ui.View):
    def __init__(self, *, category: str, page: int = 0) -> None:
        super().__init__(timeout=None)
        self.category = category
        self.page = page
        self._cooldowns: Dict[int, float] = {}

        prefix = f"price:{category}"
        self.prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:prev",
        )
        self.refresh_btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id=f"{prefix}:refresh",
        )
        self.next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:next",
        )
        self.prev_btn.callback = self.prev
        self.refresh_btn.callback = self.refresh
        self.next_btn.callback = self.next
        self.add_item(self.prev_btn)
        self.add_item(self.refresh_btn)
        self.add_item(self.next_btn)

    def set_initial_state(self, *, total_items: int) -> None:
        self.prev_btn.disabled = True
        self.next_btn.disabled = total_items <= PAGE_SIZE

    def _max_page(self, *, total_items: int) -> int:
        return max(0, (total_items - 1) // PAGE_SIZE)

    def _sync_buttons(self, *, total_items: int) -> None:
        max_page = self._max_page(total_items=total_items)
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= max_page

    async def _fetch_items(self, interaction: discord.Interaction) -> list[dict]:
        from services.items import ItemService

        if interaction.guild is None:
            return []
        ctx = get_context(interaction.guild.id)
        if ctx is None:
            return []
        return await ItemService(ctx).list_item_price_by_category(self.category)

    async def prev(self, interaction: discord.Interaction) -> None:
        if self.page > 0:
            self.page -= 1
        items = await self._fetch_items(interaction)
        self._sync_buttons(total_items=len(items))
        await interaction.response.edit_message(
            embed=price_embed(
                category=self.category,
                items=items,
                page=self.page,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )

    async def next(self, interaction: discord.Interaction) -> None:
        items = await self._fetch_items(interaction)
        max_page = self._max_page(total_items=len(items))
        if self.page < max_page:
            self.page += 1
        self._sync_buttons(total_items=len(items))
        await interaction.response.edit_message(
            embed=price_embed(
                category=self.category,
                items=items,
                page=self.page,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        user_id = interaction.user.id
        now = time.time()
        last_used = self._cooldowns.get(user_id)
        if last_used is not None:
            remaining = COOLDOWN_SECONDS - (now - last_used)
            if remaining > 0:
                await safe_respond(
                    interaction,
                    content=f"⏳ Please wait **{int(remaining)} seconds** before refreshing again.",
                    ephemeral=True,
                )
                return

        self._cooldowns[user_id] = now
        try:
            items = await self._fetch_items(interaction)
            self.page = 0
            self._sync_buttons(total_items=len(items))
            await safe_edit_message(
                interaction,
                embed=price_embed(
                    category=self.category,
                    items=items,
                    page=self.page,
                    page_size=PAGE_SIZE,
                ),
                view=self,
            )
        except Exception:
            self._cooldowns.pop(user_id, None)
            await safe_respond(
                interaction,
                content="❌ Failed to refresh price list.",
                ephemeral=True,
            )


class ClaimablePaginationView(discord.ui.View):
    def __init__(self, *, page: int = 0) -> None:
        super().__init__(timeout=None)
        self.page = page
        self._cooldowns: Dict[int, float] = {}

        prefix = "claimable"
        self.prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:prev",
        )
        self.refresh_btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id=f"{prefix}:refresh",
        )
        self.next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:next",
        )
        self.prev_btn.callback = self.prev
        self.refresh_btn.callback = self.refresh
        self.next_btn.callback = self.next
        self.add_item(self.prev_btn)
        self.add_item(self.refresh_btn)
        self.add_item(self.next_btn)

    def set_initial_state(self, *, total_items: int) -> None:
        self.prev_btn.disabled = True
        self.next_btn.disabled = total_items <= PAGE_SIZE

    def _max_page(self, total: int) -> int:
        return max(0, (total - 1) // PAGE_SIZE)

    def _sync(self, total: int) -> None:
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= self._max_page(total)

    async def _fetch_entries(self, interaction: discord.Interaction) -> list[dict]:
        from bot.handlers.market import get_market_handler

        return await get_market_handler().fetch_claimable(interaction.guild)

    async def prev(self, interaction: discord.Interaction) -> None:
        if self.page > 0:
            self.page -= 1
        entries = await self._fetch_entries(interaction)
        self._sync(len(entries))
        await interaction.response.edit_message(
            embed=claimable_embed(entries=entries, page=self.page, page_size=PAGE_SIZE),
            view=self,
        )

    async def next(self, interaction: discord.Interaction) -> None:
        entries = await self._fetch_entries(interaction)
        max_page = self._max_page(len(entries))
        if self.page < max_page:
            self.page += 1
        self._sync(len(entries))
        await interaction.response.edit_message(
            embed=claimable_embed(entries=entries, page=self.page, page_size=PAGE_SIZE),
            view=self,
        )

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        user_id = interaction.user.id
        now = time.time()
        last = self._cooldowns.get(user_id)
        if last and (now - last < COOLDOWN_SECONDS):
            await safe_respond(
                interaction,
                content=f"⏳ Please wait {int(COOLDOWN_SECONDS - (now - last))} seconds.",
                ephemeral=True,
            )
            return

        self._cooldowns[user_id] = now
        entries = await self._fetch_entries(interaction)
        self.page = 0
        self._sync(len(entries))
        await safe_edit_message(
            interaction,
            embed=claimable_embed(entries=entries, page=0, page_size=PAGE_SIZE),
            view=self,
        )


class MarketStatisticRefreshView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self._cooldowns: Dict[int, float] = {}
        self.refresh_btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id="market_stat:refresh",
        )
        self.refresh_btn.callback = self.refresh
        self.add_item(self.refresh_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    async def _fetch_embed(self, interaction: discord.Interaction) -> discord.Embed:
        from bot.handlers.market import get_market_handler

        if interaction.guild is None:
            raise RuntimeError("Guild required for market statistics")
        data = await get_market_handler().fetch_stat_data(interaction.guild)
        return market_statistic_embed(**data)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        user_id = interaction.user.id
        now = time.time()
        last_used = self._cooldowns.get(user_id)
        if last_used is not None:
            remaining = COOLDOWN_SECONDS - (now - last_used)
            if remaining > 0:
                await safe_respond(
                    interaction,
                    content=f"⏳ Please wait **{int(remaining)} seconds** before refreshing again.",
                    ephemeral=True,
                )
                return

        self._cooldowns[user_id] = now
        try:
            embed = await self._fetch_embed(interaction)
            await safe_edit_message(interaction, embed=embed, view=self)
        except Exception:
            self._cooldowns.pop(user_id, None)
            await safe_respond(
                interaction,
                content="❌ Failed to refresh market statistics.",
                ephemeral=True,
            )


class LeaderboardPaginationView(discord.ui.View):
    def __init__(self, *, lb_type: LBType, title: str, page: int = 0) -> None:
        super().__init__(timeout=None)
        self.lb_type: LBType = lb_type
        self.title = title
        self.page = page
        self._cooldowns: Dict[int, float] = {}

        prefix = f"leaderboard:{self.lb_type}"
        self.prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:prev",
        )
        self.refresh_btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id=f"{prefix}:refresh",
        )
        self.next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:next",
        )
        self.prev_btn.callback = self.prev
        self.refresh_btn.callback = self.refresh
        self.next_btn.callback = self.next
        self.add_item(self.prev_btn)
        self.add_item(self.refresh_btn)
        self.add_item(self.next_btn)

    def set_initial_state(self, *, total_items: int) -> None:
        self.prev_btn.disabled = True
        self.next_btn.disabled = total_items <= PAGE_SIZE

    def _max_page(self, *, total_items: int) -> int:
        return max(0, (total_items - 1) // PAGE_SIZE)

    def _sync_buttons(self, *, total_items: int) -> None:
        max_page = self._max_page(total_items=total_items)
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= max_page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    def _sync_lb_type_from_interaction(self, interaction: discord.Interaction) -> None:
        data = interaction.data or {}
        custom_id = data.get("custom_id")
        if not isinstance(custom_id, str):
            return
        parts = custom_id.split(":")
        if len(parts) >= 3:
            lb_type = parts[1]
            if lb_type in ("worker", "customer", "item", "donor"):
                self.lb_type = cast(LBType, lb_type)

    async def _fetch_entries(self, interaction: discord.Interaction) -> list[dict]:
        from bot.handlers.market import get_market_handler

        self._sync_lb_type_from_interaction(interaction)
        return await get_market_handler().fetch_entries(self.lb_type, interaction.guild)

    async def prev(self, interaction: discord.Interaction) -> None:
        if self.page > 0:
            self.page -= 1
        entries = await self._fetch_entries(interaction)
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def next(self, interaction: discord.Interaction) -> None:
        entries = await self._fetch_entries(interaction)
        max_page = self._max_page(total_items=len(entries))
        if self.page < max_page:
            self.page += 1
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        user_id = interaction.user.id
        now = time.time()
        last_used = self._cooldowns.get(user_id)
        if last_used is not None:
            remaining = COOLDOWN_SECONDS - (now - last_used)
            if remaining > 0:
                await safe_respond(
                    interaction,
                    content=f"⏳ Please wait **{int(remaining)} seconds** before refreshing again.",
                    ephemeral=True,
                )
                return

        self._cooldowns[user_id] = now
        try:
            entries = await self._fetch_entries(interaction)
            self.page = 0
            self._sync_buttons(total_items=len(entries))
            await safe_edit_message(
                interaction,
                embed=leaderboard_embed(
                    title=self.title,
                    entries=entries,
                    lb_type=cast(LBType, self.lb_type),
                    page=self.page,
                    page_size=PAGE_SIZE,
                ),
                view=self,
            )
        except Exception:
            self._cooldowns.pop(user_id, None)
            await safe_respond(
                interaction,
                content="❌ Failed to refresh leaderboard.",
                ephemeral=True,
            )

    async def _update(self, interaction: discord.Interaction, *, entries: list[dict]) -> None:
        await interaction.response.edit_message(
            embed=leaderboard_embed(
                title=self.title,
                entries=entries,
                lb_type=cast(LBType, self.lb_type),
                page=self.page,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )


class RatedLeaderboardPaginationView(discord.ui.View):
    def __init__(self, *, page: int = 0) -> None:
        super().__init__(timeout=None)
        self.page = page
        self._cooldowns: Dict[int, float] = {}

        prefix = "leaderboard:rated"
        self.prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:prev",
        )
        self.refresh_btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            custom_id=f"{prefix}:refresh",
        )
        self.next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:next",
        )
        self.prev_btn.callback = self.prev
        self.refresh_btn.callback = self.refresh
        self.next_btn.callback = self.next
        self.add_item(self.prev_btn)
        self.add_item(self.refresh_btn)
        self.add_item(self.next_btn)

    def set_initial_state(self, *, total_items: int) -> None:
        self.prev_btn.disabled = True
        self.next_btn.disabled = total_items <= PAGE_SIZE

    def _max_page(self, *, total_items: int) -> int:
        return max(0, (total_items - 1) // PAGE_SIZE)

    def _sync_buttons(self, *, total_items: int) -> None:
        max_page = self._max_page(total_items=total_items)
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= max_page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    async def _fetch_entries(self, interaction: discord.Interaction) -> list[dict]:
        from bot.handlers.market import get_market_handler

        return (await get_market_handler().fetch_rated_workers(interaction.guild))[:MAX_ITEMS]

    async def prev(self, interaction: discord.Interaction) -> None:
        if self.page > 0:
            self.page -= 1
        entries = await self._fetch_entries(interaction)
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def next(self, interaction: discord.Interaction) -> None:
        entries = await self._fetch_entries(interaction)
        max_page = self._max_page(total_items=len(entries))
        if self.page < max_page:
            self.page += 1
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def refresh(self, interaction: discord.Interaction) -> None:
        await safe_defer(interaction, ephemeral=True)
        user_id = interaction.user.id
        now = time.time()
        last_used = self._cooldowns.get(user_id)
        if last_used is not None:
            remaining = COOLDOWN_SECONDS - (now - last_used)
            if remaining > 0:
                await safe_respond(
                    interaction,
                    content=f"⏳ Please wait **{int(remaining)} seconds** before refreshing again.",
                    ephemeral=True,
                )
                return

        self._cooldowns[user_id] = now
        try:
            entries = await self._fetch_entries(interaction)
            self.page = 0
            self._sync_buttons(total_items=len(entries))
            await safe_edit_message(
                interaction,
                embed=rated_leaderboard_embed(
                    title="⭐ Top Rated Workers",
                    entries=entries,
                    page=self.page,
                    page_size=PAGE_SIZE,
                ),
                view=self,
            )
        except Exception:
            self._cooldowns.pop(user_id, None)
            await safe_respond(
                interaction,
                content="❌ Failed to refresh rated leaderboard.",
                ephemeral=True,
            )

    async def _update(self, interaction: discord.Interaction, *, entries: list[dict]) -> None:
        await safe_edit_message(
            interaction,
            embed=rated_leaderboard_embed(
                title="⭐ Top Rated Workers",
                entries=entries,
                page=self.page,
                page_size=PAGE_SIZE,
            ),
            view=self,
        )
