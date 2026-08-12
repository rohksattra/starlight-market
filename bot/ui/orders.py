"""Order embeds, buttons, and modals (UI only)."""
from __future__ import annotations

from typing import Awaitable, Callable, Literal
from uuid import uuid4

import discord
from discord.errors import NotFound

from bot.ui.shared import button_notice_content_suffix, set_starlight_footer
from core.constants import DONOR_COUPON_DISCOUNT_RATE
from core.tenant import GameContext
from utils.assets import item_image_url


def fmt(value: int) -> str:
    return f"{value:,}"


def customer_payment_total(
    *,
    item_price: int,
    quantity: int,
    coupon_applied: bool = False,
) -> int:
    total = item_price * quantity
    if coupon_applied:
        total = int(total * (1 - DONOR_COUPON_DISCOUNT_RATE))
    return total


def customer_total_price(order: dict) -> int:
    return customer_payment_total(
        item_price=int(order.get("item_price", 0)),
        quantity=int(order.get("item_quantity", 0)),
        coupon_applied=bool(order.get("coupon_applied")),
    )


def order_description(order: dict) -> str:
    customer_id = order.get("customer_id")
    item_name = order.get("item_name", "Item")
    item_price = int(order.get("item_price", 0))
    quantity = int(order.get("item_quantity", 0))
    order_claims = order.get("order_claims", {})
    delivered = int(order_claims.get("order_delivered", 0))
    completed = int(order_claims.get("order_completed", 0))
    claimable = int(order_claims.get("order_claimable", 0))
    worker_claims = {
        wid: int(qty)
        for wid, qty in order.get("worker_claims", {}).items()
        if int(qty) > 0
    }
    claimed_total = sum(worker_claims.values())
    total_line = f"- 🪙 ***{fmt(customer_total_price(order))}***"
    if order.get("coupon_applied"):
        total_line += " *(0.5% donor coupon applied)*"
    claimed_lines = (
        "\n".join(f"🏷 ***{fmt(qty)}*** by <@{worker_id}>" for worker_id, qty in worker_claims.items())
        if worker_claims
        else "***🏷 0***"
    )
    return (
        f"**Customer**\n"
        f"- ***<@{customer_id}>***\n"
        f"**Item**\n"
        f"- ***{item_name}***\n"
        f"**Quantity**\n"
        f"- 🏷 ***{fmt(quantity)}***\n"
        f"**Price**\n"
        f"- 🪙 ***{fmt(item_price)} each***\n"
        f"**Estimated Total**\n"
        f"{total_line}\n\n"
        f"**__Delivered__**\n"
        f"-# Items delivered to the customer\n"
        f"🏷 ***{fmt(delivered)}***\n\n"
        f"**__Completed__**\n"
        f"-# Items finished by the workers\n"
        f"🏷 ***{fmt(completed)}***\n\n"
        f"**__Claimed__**\n"
        f"-# Items being processed by workers\n"
        f"{claimed_lines}\n"
        f"-# Total claimed\n"
        f"🏷 ***{fmt(claimed_total)}***\n\n"
        f"**__Claimable__**\n"
        f"-# Items available for workers to claim\n"
        f"🏷 ***{fmt(claimable)}***\n\n"
        f"Workers can accept the order using **/claim**\n"
        f"or cancel with **/unclaim**"
    )


def _item_image_url(ctx: GameContext, item_image: str, item_category: str) -> str:
    return item_image_url(ctx, item_image=item_image, item_category=item_category)


def order_embed(
    *,
    order: dict,
    ctx: GameContext,
    guild: discord.Guild,
) -> tuple[str, discord.Embed]:
    quantity = int(order.get("item_quantity", 0))
    item_name = order.get("item_name", "Item")
    worker_role = guild.get_role(ctx.roles.worker)
    worker_mention = worker_role.mention if worker_role else "@Worker"
    embed = discord.Embed(
        title=f"📦 New Order — ***{fmt(quantity)}x {item_name}***",
        description=order_description(order),
        color=0xFFD700,
    )
    image_url = _item_image_url(ctx, order.get("item_image", ""), order.get("item_category", ""))
    if image_url:
        embed.set_thumbnail(url=image_url)
    set_starlight_footer(embed, detail="Good Luck 💪 & Have Fun 🙃")
    return f"🔊 {worker_mention}", embed


async def update_order_embed(
    *,
    channel: discord.TextChannel,
    order: dict,
    ctx: GameContext,
) -> None:
    embed_message_id = order.get("embed_message_id")
    if not embed_message_id:
        return
    try:
        msg = await channel.fetch_message(int(embed_message_id))
    except discord.NotFound:
        return
    guild = channel.guild
    worker_role = guild.get_role(ctx.roles.worker) if guild else None
    worker_mention = worker_role.mention if worker_role else "@Worker"
    quantity = int(order.get("item_quantity", 0))
    item_name = order.get("item_name", "Item")
    embed = discord.Embed(
        title=f"📦 New Order — ***{fmt(quantity)}x {item_name}***",
        description=order_description(order),
        color=0xFFD700,
    )
    image_url = _item_image_url(ctx, order.get("item_image", ""), order.get("item_category", ""))
    if image_url:
        embed.set_thumbnail(url=image_url)
    set_starlight_footer(embed, detail="Good Luck 💪 & Have Fun 🙃")
    await msg.edit(content=f"🔊 {worker_mention}", embed=embed)


def order_entry_embed(role_mention: str) -> discord.Embed:
    embed = discord.Embed(
        description=(
            "Welcome to 🌟 **Starlight Market** 🛒\n\n"
            "1️⃣ Click **Order Now**\n"
            "2️⃣ Select category & item\n"
            "3️⃣ Enter quantity\n"
            "4️⃣ Confirm order\n\n"
            f"For custom orders, contact {role_mention}"
        ),
        color=0xFFD700,
    )
    set_starlight_footer(embed)
    return embed


def claim_log_embed(
    *,
    worker: discord.Member,
    item_name: str,
    quantity: int,
    channel: discord.TextChannel,
    action: str,
    item_emoji: str = "🌟",
    staff: discord.Member | None = None,
) -> discord.Embed:
    emoji = item_emoji or "🌟"
    qty = f"***{quantity:,}x***"
    item = f"***{emoji} {item_name}***"
    place = f"***{channel.mention}***"
    worker_m = f"***{worker.mention}***"
    staff_m = f"***{staff.mention}***" if staff else "***Staff***"

    if action == "claim":
        text = f"{worker_m} has claimed 🏷 {qty} of {item} in {place}"
    elif action == "unclaim":
        text = f"{worker_m} has unclaimed 🏷 {qty} of {item} in {place}"
    elif action == "force_claim":
        text = f"{staff_m} forced {worker_m} to claim 🏷 {qty} of {item} in {place}"
    elif action == "force_unclaim":
        text = f"{staff_m} forced {worker_m} to unclaim 🏷 {qty} of {item} in {place}"
    else:
        text = "Unknown claim action."

    embed = discord.Embed(
        title="📌 Order Claim Update",
        description=text,
        color=0xFFD700,
    )
    embed.set_footer(text="🌟 Starlight Market")
    return embed


def order_update_embed(
    *,
    field: Literal["price", "quantity", "customer"],
    old_value: int | str,
    new_value: int | str,
    worker_role: discord.Role | None,
) -> tuple[str, discord.Embed]:
    role_mention = worker_role.mention if worker_role else "@Worker"

    if field == "quantity":
        body = (
            f"🏷 **Quantity updated:** ***{int(old_value):,}*** ➡️ ***{int(new_value):,}***"
        )
    elif field == "price":
        body = (
            f"🪙 **Price updated:** ***{int(old_value):,}*** ➡️ ***{int(new_value):,}***"
        )
    elif field == "customer":
        body = f"👤 **Customer updated:** <@{old_value}> ➡️ <@{new_value}>"
    else:
        raise ValueError("Invalid field for order update embed")

    embed = discord.Embed(title="📌 Order Update", description=body, color=0xFFD700)
    embed.set_footer(text="🌟 Starlight Market")
    return f"🔔 {role_mention}", embed


class OrderEntryView(discord.ui.View):
    def __init__(self, on_start: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=None)
        self.on_start = on_start

    @discord.ui.button(label="🛒 Order Now", style=discord.ButtonStyle.primary, custom_id="order:entry:start")
    async def order_now(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        from utils.discord_safe import safe_defer

        await safe_defer(interaction, ephemeral=True)
        await self.on_start(interaction)


class OrderClaimView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.claim_btn = discord.ui.Button(
            label="Claim",
            style=discord.ButtonStyle.success,
            custom_id="orderclaim:claim",
        )
        self.unclaim_btn = discord.ui.Button(
            label="Unclaim",
            style=discord.ButtonStyle.danger,
            custom_id="orderclaim:unclaim",
        )
        self.refresh_btn = discord.ui.Button(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            custom_id="orderclaim:refresh",
        )
        self.claim_btn.callback = self.claim
        self.unclaim_btn.callback = self.unclaim
        self.refresh_btn.callback = self.refresh
        self.add_item(self.claim_btn)
        self.add_item(self.unclaim_btn)
        self.add_item(self.refresh_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    async def claim(self, interaction: discord.Interaction) -> None:
        from bot.handlers.orders import get_order_handler

        async def on_submit(inter2: discord.Interaction, qty: int) -> None:
            try:
                await get_order_handler().handle_claim_action(inter2, action="claim", quantity=qty)
            except Exception:
                from utils.discord_safe import safe_respond

                await safe_respond(inter2, content="❌ Failed to claim.", ephemeral=True)

        await interaction.response.send_modal(QuantityModal(on_submit=on_submit))

    async def unclaim(self, interaction: discord.Interaction) -> None:
        from bot.handlers.orders import get_order_handler

        async def on_submit(inter2: discord.Interaction, qty: int) -> None:
            try:
                await get_order_handler().handle_claim_action(inter2, action="unclaim", quantity=qty)
            except Exception:
                from utils.discord_safe import safe_respond

                await safe_respond(inter2, content="❌ Failed to unclaim.", ephemeral=True)

        await interaction.response.send_modal(QuantityModal(on_submit=on_submit))

    async def refresh(self, interaction: discord.Interaction) -> None:
        from bot.handlers.orders import get_order_handler
        from utils.discord_safe import safe_defer, safe_respond

        await safe_defer(interaction, ephemeral=True)
        try:
            await get_order_handler().handle_claim_refresh(interaction)
            await safe_respond(interaction, content="✅ Refreshed.", ephemeral=True)
        except Exception:
            await safe_respond(interaction, content="❌ Failed to refresh.", ephemeral=True)


class QuantityModal(discord.ui.Modal, title="Quantity"):
    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="Enter number",
        required=True,
    )

    def __init__(self, on_submit: Callable[[discord.Interaction, int], Awaitable[None]]) -> None:
        super().__init__()
        self._cb = on_submit

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from utils.discord_safe import safe_respond

        try:
            qty = int(self.quantity.value)
        except ValueError:
            await safe_respond(interaction, content="❌ Quantity must be a number.", ephemeral=True)
            return
        if qty <= 0:
            await safe_respond(interaction, content="❌ Quantity must be greater than 0.", ephemeral=True)
            return
        await self._cb(interaction, qty)


MORE = "__more__"
PREV = "__prev__"


class OrderCategoryView(discord.ui.View):
    def __init__(
        self,
        *,
        user_id: int,
        categories: list[str],
        page: int,
        page_size: int,
        on_select: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.categories = categories
        self.page = page
        self.page_size = page_size
        self.on_select = on_select
        self.select = discord.ui.Select(placeholder="Select category", min_values=1, max_values=1)
        self.select.callback = self._handle
        self.add_item(self.select)
        self._render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    def _render(self) -> None:
        start = self.page * self.page_size
        end = start + self.page_size
        slice_ = self.categories[start:end]
        options: list[discord.SelectOption] = []
        for category in slice_:
            options.append(discord.SelectOption(label=category[:100], value=category))
        if end < len(self.categories):
            options.append(discord.SelectOption(label="➡️ More...", value=MORE))
        if self.page > 0:
            options.append(discord.SelectOption(label="⬅️ Previous...", value=PREV))
        self.select.options = options

    async def _handle(self, interaction: discord.Interaction) -> None:
        from utils.discord_safe import safe_edit_message

        value = self.select.values[0]
        if value == MORE:
            await safe_edit_message(
                interaction,
                view=OrderCategoryView(
                    user_id=self.user_id,
                    categories=self.categories,
                    page=self.page + 1,
                    page_size=self.page_size,
                    on_select=self.on_select,
                ),
            )
            return
        if value == PREV:
            await safe_edit_message(
                interaction,
                view=OrderCategoryView(
                    user_id=self.user_id,
                    categories=self.categories,
                    page=self.page - 1,
                    page_size=self.page_size,
                    on_select=self.on_select,
                ),
            )
            return
        await self.on_select(interaction, value)


class OrderItemView(discord.ui.View):
    def __init__(
        self,
        *,
        user_id: int,
        items: list[dict],
        page: int,
        page_size: int,
        on_pick: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.items = items
        self.page = page
        self.page_size = page_size
        self.on_pick = on_pick
        self.select = discord.ui.Select(placeholder="Select item", min_values=1, max_values=1)
        self.select.callback = self._handle
        self.add_item(self.select)
        self._render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    def _render(self) -> None:
        start = self.page * self.page_size
        end = start + self.page_size
        slice_ = self.items[start:end]
        options: list[discord.SelectOption] = []
        for it in slice_:
            raw = it.get("item_emoji", "🌟") or "🌟"
            name = str(it.get("item_name", "Item"))
            emoji: str | discord.PartialEmoji | None = raw
            if isinstance(raw, str) and raw.startswith("<"):
                try:
                    emoji = discord.PartialEmoji.from_str(raw)
                except Exception:
                    emoji = None
            options.append(
                discord.SelectOption(
                    label=name[:100],
                    value=str(it.get("item_id")),
                    description=f"🪙 {int(it.get('item_price', 0)):,}",
                    emoji=emoji,
                )
            )
        if end < len(self.items):
            options.append(discord.SelectOption(label="➡️ More...", value=MORE))
        if self.page > 0:
            options.append(discord.SelectOption(label="⬅️ Previous...", value=PREV))
        self.select.options = options

    async def _handle(self, interaction: discord.Interaction) -> None:
        from utils.discord_safe import safe_edit_message

        value = self.select.values[0]
        if value == MORE:
            await safe_edit_message(
                interaction,
                view=OrderItemView(
                    user_id=self.user_id,
                    items=self.items,
                    page=self.page + 1,
                    page_size=self.page_size,
                    on_pick=self.on_pick,
                ),
            )
            return
        if value == PREV:
            await safe_edit_message(
                interaction,
                view=OrderItemView(
                    user_id=self.user_id,
                    items=self.items,
                    page=self.page - 1,
                    page_size=self.page_size,
                    on_pick=self.on_pick,
                ),
            )
            return
        await self.on_pick(interaction, value)


class OrderConfirmView(discord.ui.View):
    def __init__(self, on_confirm: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=180)
        self.on_confirm = on_confirm
        self.message: discord.Message | None = None

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        from utils.discord_safe import safe_defer, safe_edit_message

        await safe_defer(interaction)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await safe_edit_message(interaction, view=self)
        await self.on_confirm(interaction)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        from utils.discord_safe import safe_defer, safe_edit_message, safe_respond

        await safe_defer(interaction, ephemeral=True)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await safe_edit_message(interaction, view=self)
        await safe_respond(interaction, content="❌ Order canceled.", ephemeral=True)
        self.stop()

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            if self.message:
                await self.message.edit(
                    content="⏰ **Session expired. Please create the order again.**",
                    view=self,
                )
        except NotFound:
            pass
        self.stop()


def transaction_embed(
    *,
    role: str,
    member: discord.Member,
    order: dict,
    quantity: int,
    ctx: GameContext,
    item_emoji: str = "🌟",
) -> discord.Embed:
    item_name: str = order.get("item_name", "Item")
    emoji: str = item_emoji or "🌟"
    price: int = int(order.get("item_price", 0))
    quantity = int(quantity)
    coupon_applied = bool(order.get("coupon_applied"))

    item_fmt = f"{emoji} {item_name}"
    qty_fmt = f"🏷 ***{fmt(quantity)}x***"
    keep_rate = 1.0 - float(ctx.economy.worker_fee_rate)

    if role == "worker":
        amount = int(price * quantity * keep_rate)
        description = (
            f"***Starlight Market*** paid 🪙 ***{fmt(amount)}*** to "
            f"{member.mention} for {qty_fmt} of ***{item_fmt}***."
        )
    else:
        amount = customer_payment_total(
            item_price=price,
            quantity=quantity,
            coupon_applied=coupon_applied,
        )
        coupon_note = " *(0.5% donor coupon applied)*" if coupon_applied else ""
        description = (
            f"{member.mention} spent 🪙 ***{fmt(amount)}***{coupon_note} for "
            f"{qty_fmt} of ***{item_fmt}*** at ***Starlight Market***."
        )

    embed = discord.Embed(
        title="💰 Transaction Record",
        description=description,
        color=0xFFD700,
    )
    set_starlight_footer(embed, include_button_notice=False)
    return embed


def pickup_embed(
    *,
    customer_mention: str,
    bank_manager_role_id: int,
    item_name: str,
    item_price: int,
    quantity: int,
    item_emoji: str = "🌟",
    coupon_applied: bool = False,
) -> tuple[str, discord.Embed]:
    bank_manager_mention = f"<@&{bank_manager_role_id}>"
    amount = customer_payment_total(
        item_price=item_price,
        quantity=quantity,
        coupon_applied=coupon_applied,
    )
    item_fmt = f"{item_emoji} {item_name}"
    qty_fmt = f"🏷 ***{fmt(quantity)}x***"
    total_fmt = f"🪙 ***{fmt(amount)}***"
    if coupon_applied:
        total_fmt += " *(0.5% donor coupon applied)*"

    embed = discord.Embed(
        title="📦 Order Ready for Pickup",
        description=(
            f"Your {qty_fmt} of ***{item_fmt}*** is ready.\n"
            f"Total Price {total_fmt}\n\n"
            f"Please ping {bank_manager_mention} to pickup your order.\n\n"
            f"You have ⏳ ***7 days*** to pickup or to inform Bank Manager when will you pickup the order. "
            f"If no information after the time, the Market will sell the items."
        ),
        color=0xFFD700,
    )
    set_starlight_footer(embed, include_button_notice=False)
    return f"🔔 {customer_mention}", embed


def close_embed(*, bank_manager_role_id: int) -> discord.Embed:
    bank_manager_mention = f"<@&{bank_manager_role_id}>"
    embed = discord.Embed(
        title="✅ Order Ready to be Closed",
        description=(
            "All items have been **successfully delivered**.\n\n"
            f"{bank_manager_mention} may now click **Close Order** "
            "to finalize and remove this order."
        ),
        color=0xFFD700,
    )
    set_starlight_footer(embed, include_button_notice=False)
    return embed


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
    *,
    worker: discord.Member,
    customer: discord.Member,
    item_name: str,
    item_quantity: int,
    order_channel: discord.TextChannel,
    item_emoji: str = "🌟",
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
    set_starlight_footer(embed, include_button_notice=False)
    return f"🔔 {customer.mention}", embed


def worker_rating_summary(*, average: float, count: int) -> str:
    if count <= 0:
        return "No ratings yet"
    stars = format_rating_stars(average)
    return (
        f"{stars} ***{average:.2f}***\n"
        f"***{fmt(count)}*** rating(s)"
    )


CLOSE_ORDER_CUSTOM_ID = "orderclose:close"
CONFIRM_TIMEOUT_SECONDS = 30


class OrderCloseConfirmView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=CONFIRM_TIMEOUT_SECONDS)
        self.message: discord.Message | None = None
        token = uuid4().hex[:8]

        yes_btn = discord.ui.Button(
            label="Yes",
            style=discord.ButtonStyle.success,
            custom_id=f"orderclose:yes:{token}",
        )
        no_btn = discord.ui.Button(
            label="No",
            style=discord.ButtonStyle.secondary,
            custom_id=f"orderclose:no:{token}",
        )
        yes_btn.callback = self._yes
        no_btn.callback = self._no
        self.add_item(yes_btn)
        self.add_item(no_btn)

    async def _delete_message(self) -> None:
        if self.message is None:
            return
        try:
            await self.message.delete()
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        await self._delete_message()

    async def _yes(self, interaction: discord.Interaction) -> None:
        from bot.handlers.orders import get_order_handler
        from utils.discord_safe import safe_defer, safe_respond

        if not isinstance(interaction.channel, discord.TextChannel):
            await safe_respond(interaction, content="❌ Invalid channel.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        self.stop()

        await safe_defer(interaction, ephemeral=True)
        await self._delete_message()

        try:
            await get_order_handler().finalize_close_order(interaction, channel=interaction.channel)
        except Exception:
            await safe_respond(interaction, content="❌ Failed to close order.", ephemeral=True)

    async def _no(self, interaction: discord.Interaction) -> None:
        from utils.discord_safe import safe_defer, safe_respond

        for child in self.children:
            child.disabled = True
        self.stop()
        await safe_defer(interaction, ephemeral=True)
        await self._delete_message()
        await safe_respond(interaction, content="❌ Order close cancelled.", ephemeral=True)


class OrderCloseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        btn = discord.ui.Button(
            label="Close Order",
            style=discord.ButtonStyle.danger,
            custom_id=CLOSE_ORDER_CUSTOM_ID,
        )
        btn.callback = self.close_order
        self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    async def close_order(self, interaction: discord.Interaction) -> None:
        from bot.handlers.orders import get_order_handler

        await get_order_handler().handle_close_order_button(interaction)


class RatingWorkerButton(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _handle(self, interaction: discord.Interaction, rating: int) -> None:
        from bot.handlers.orders import get_order_handler
        from utils.discord_safe import safe_defer, safe_respond

        await safe_defer(interaction, ephemeral=True)
        if interaction.message is None:
            await safe_respond(interaction, content="❌ Message not found.", ephemeral=True)
            return
        await get_order_handler().handle_rating(interaction, rating=rating)

    @discord.ui.button(label="⭐ 1", style=discord.ButtonStyle.secondary, custom_id="rating:worker:1")
    async def r1(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, 1)

    @discord.ui.button(label="⭐ 2", style=discord.ButtonStyle.secondary, custom_id="rating:worker:2")
    async def r2(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, 2)

    @discord.ui.button(label="⭐ 3", style=discord.ButtonStyle.secondary, custom_id="rating:worker:3")
    async def r3(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, 3)

    @discord.ui.button(label="⭐ 4", style=discord.ButtonStyle.secondary, custom_id="rating:worker:4")
    async def r4(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, 4)

    @discord.ui.button(label="⭐ 5", style=discord.ButtonStyle.secondary, custom_id="rating:worker:5")
    async def r5(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, 5)
