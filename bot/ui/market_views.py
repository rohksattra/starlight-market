"""Market pagination and refresh views."""
from __future__ import annotations

import logging
import time
from typing import Dict, cast

import discord

from bot.ui.market_embeds import (
    COOLDOWN_SECONDS,
    LBType,
    MAX_ITEMS,
    PAGE_SIZE,
    _apply_period_styles,
    _attach_period_buttons,
    _page_from_message,
    _sync_period_from_interaction,
    claimable_embed,
    leaderboard_embed,
    market_statistic_embed,
    price_embed,
    rated_leaderboard_embed,
)
from bot.ui.shared import ctx_from_interaction
from core.period import StatPeriod
from core.tenant import get_context
from utils.discord_safe import safe_defer, safe_edit_message, safe_respond

log = logging.getLogger("bot.ui.market")

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
                ctx=ctx_from_interaction(interaction),
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
                ctx=ctx_from_interaction(interaction),
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
                    ctx=ctx_from_interaction(interaction),
                ),
                view=self,
            )
        except Exception:
            log.exception("Failed to refresh price list")
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
            embed=claimable_embed(
                entries=entries,
                page=self.page,
                page_size=PAGE_SIZE,
                ctx=ctx_from_interaction(interaction),
            ),
            view=self,
        )

    async def next(self, interaction: discord.Interaction) -> None:
        entries = await self._fetch_entries(interaction)
        max_page = self._max_page(len(entries))
        if self.page < max_page:
            self.page += 1
        self._sync(len(entries))
        await interaction.response.edit_message(
            embed=claimable_embed(
                entries=entries,
                page=self.page,
                page_size=PAGE_SIZE,
                ctx=ctx_from_interaction(interaction),
            ),
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
            embed=claimable_embed(
                entries=entries,
                page=0,
                page_size=PAGE_SIZE,
                ctx=ctx_from_interaction(interaction),
            ),
            view=self,
        )


class MarketStatisticRefreshView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.period: StatPeriod = "all"
        _attach_period_buttons(self, prefix="market_stat", row=0)
        _apply_period_styles(self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    async def _fetch_embed(self, interaction: discord.Interaction) -> discord.Embed:
        from bot.handlers.market import get_market_handler

        if interaction.guild is None:
            raise RuntimeError("Guild required for market statistics")
        data = await get_market_handler().fetch_stat_data(
            interaction.guild, period=self.period
        )
        return market_statistic_embed(**data)

    async def on_period_selected(self, interaction: discord.Interaction) -> None:
        _apply_period_styles(self)
        try:
            embed = await self._fetch_embed(interaction)
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            log.exception("Failed to update market statistics")
            await safe_respond(
                interaction,
                content="❌ Failed to update market statistics.",
                ephemeral=True,
            )


class LeaderboardPaginationView(discord.ui.View):
    def __init__(self, *, lb_type: LBType, title: str, page: int = 0) -> None:
        super().__init__(timeout=None)
        self.lb_type: LBType = lb_type
        self.title = title
        self.page = page
        self.period: StatPeriod = "all"

        prefix = f"leaderboard:{self.lb_type}"
        _attach_period_buttons(self, prefix=prefix, row=0)
        self.prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:prev",
            row=0,
        )
        self.next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:next",
            row=0,
        )
        self.prev_btn.callback = self.prev
        self.next_btn.callback = self.next
        self.add_item(self.prev_btn)
        self.add_item(self.next_btn)
        _apply_period_styles(self)

    def set_initial_state(self, *, total_items: int) -> None:
        self.prev_btn.disabled = True
        self.next_btn.disabled = total_items <= PAGE_SIZE
        _apply_period_styles(self)

    def _max_page(self, *, total_items: int) -> int:
        return max(0, (total_items - 1) // PAGE_SIZE)

    def _sync_buttons(self, *, total_items: int) -> None:
        max_page = self._max_page(total_items=total_items)
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= max_page
        _apply_period_styles(self)

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
        _sync_period_from_interaction(self, interaction)
        return await get_market_handler().fetch_entries(
            self.lb_type, interaction.guild, period=self.period
        )

    async def on_period_selected(self, interaction: discord.Interaction) -> None:
        self.page = 0
        entries = await self._fetch_entries(interaction)
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def prev(self, interaction: discord.Interaction) -> None:
        current = _page_from_message(interaction)
        if current is not None:
            self.page = current
        if self.page > 0:
            self.page -= 1
        entries = await self._fetch_entries(interaction)
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def next(self, interaction: discord.Interaction) -> None:
        current = _page_from_message(interaction)
        if current is not None:
            self.page = current
        entries = await self._fetch_entries(interaction)
        max_page = self._max_page(total_items=len(entries))
        if self.page < max_page:
            self.page += 1
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def _update(self, interaction: discord.Interaction, *, entries: list[dict]) -> None:
        await interaction.response.edit_message(
            embed=leaderboard_embed(
                title=self.title,
                entries=entries,
                lb_type=cast(LBType, self.lb_type),
                page=self.page,
                page_size=PAGE_SIZE,
                period=self.period,
                ctx=ctx_from_interaction(interaction),
            ),
            view=self,
        )


class RatedLeaderboardPaginationView(discord.ui.View):
    def __init__(self, *, page: int = 0) -> None:
        super().__init__(timeout=None)
        self.page = page
        self.period: StatPeriod = "all"

        prefix = "leaderboard:rated"
        _attach_period_buttons(self, prefix=prefix, row=0)
        self.prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:prev",
            row=0,
        )
        self.next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{prefix}:next",
            row=0,
        )
        self.prev_btn.callback = self.prev
        self.next_btn.callback = self.next
        self.add_item(self.prev_btn)
        self.add_item(self.next_btn)
        _apply_period_styles(self)

    def set_initial_state(self, *, total_items: int) -> None:
        self.prev_btn.disabled = True
        self.next_btn.disabled = total_items <= PAGE_SIZE
        _apply_period_styles(self)

    def _max_page(self, *, total_items: int) -> int:
        return max(0, (total_items - 1) // PAGE_SIZE)

    def _sync_buttons(self, *, total_items: int) -> None:
        max_page = self._max_page(total_items=total_items)
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= max_page
        _apply_period_styles(self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    async def _fetch_entries(self, interaction: discord.Interaction) -> list[dict]:
        from bot.handlers.market import get_market_handler

        _sync_period_from_interaction(self, interaction)
        return (
            await get_market_handler().fetch_rated_workers(
                interaction.guild, period=self.period
            )
        )[:MAX_ITEMS]

    async def on_period_selected(self, interaction: discord.Interaction) -> None:
        self.page = 0
        entries = await self._fetch_entries(interaction)
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def prev(self, interaction: discord.Interaction) -> None:
        current = _page_from_message(interaction)
        if current is not None:
            self.page = current
        if self.page > 0:
            self.page -= 1
        entries = await self._fetch_entries(interaction)
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def next(self, interaction: discord.Interaction) -> None:
        current = _page_from_message(interaction)
        if current is not None:
            self.page = current
        entries = await self._fetch_entries(interaction)
        max_page = self._max_page(total_items=len(entries))
        if self.page < max_page:
            self.page += 1
        self._sync_buttons(total_items=len(entries))
        await self._update(interaction, entries=entries)

    async def _update(self, interaction: discord.Interaction, *, entries: list[dict]) -> None:
        await safe_edit_message(
            interaction,
            embed=rated_leaderboard_embed(
                title="⭐ Top Rated Workers",
                entries=entries,
                page=self.page,
                page_size=PAGE_SIZE,
                period=self.period,
                ctx=ctx_from_interaction(interaction),
            ),
            view=self,
        )
