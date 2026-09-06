from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot.handlers.order_presenters import (
    after_income_recorded,
    sync_order_category,
    target_order_category_id,
)
from bot.handlers.orders import OrderHandler
from core.tenant import all_contexts, load_all_tenants
from models.enums import OrderStatus
from tests.integration.mongo import make_test_context, sample_order


def _run(coro):
    return asyncio.run(coro)


def _ctx(*, new_id: int = 11, claimed_id: int = 22, completed_id: int = 33, game: str = "coa"):
    ctx = make_test_context("discord-test", game=game)
    return replace(
        ctx,
        channels=replace(
            ctx.channels,
            new_orders_category=new_id,
            claimed_orders_category=claimed_id,
            completed_orders_category=completed_id,
        ),
    )


def _order(*, status: OrderStatus, quantity: int = 10, claimable: int) -> dict:
    order = sample_order(item_quantity=quantity)
    order["order_status"] = status
    order["order_claims"]["order_claimable"] = claimable
    order["order_claims"]["order_claimed"] = quantity - claimable
    return order


def test_target_category_new_when_fully_unclaimed() -> None:
    ctx = _ctx()
    order = _order(status=OrderStatus.CLAIMED, claimable=10)
    assert target_order_category_id(order, ctx) == ctx.channels.new_orders_category


def test_target_category_claimed_when_partial() -> None:
    ctx = _ctx()
    order = _order(status=OrderStatus.CLAIMED, claimable=7)
    assert target_order_category_id(order, ctx) == ctx.channels.claimed_orders_category


def test_target_category_skips_completed_status() -> None:
    ctx = _ctx()
    order = _order(status=OrderStatus.COMPLETED, claimable=0)
    assert target_order_category_id(order, ctx) is None


def test_eop_and_coa_use_their_own_category_ids() -> None:
    load_all_tenants()
    games = {ctx.game: ctx for ctx in all_contexts()}
    assert set(games) == {"coa", "eop"}
    for ctx in games.values():
        ids = {
            ctx.channels.new_orders_category,
            ctx.channels.claimed_orders_category,
            ctx.channels.completed_orders_category,
        }
        assert 0 not in ids
        assert len(ids) == 3
    assert games["coa"].channels.new_orders_category != games["eop"].channels.new_orders_category
    eop_claimed = _order(status=OrderStatus.CLAIMED, claimable=4)
    assert target_order_category_id(eop_claimed, games["eop"]) == games["eop"].channels.claimed_orders_category


def test_sync_moves_channel_to_claimed_category() -> None:
    ctx = _ctx()
    claimed = MagicMock(spec=discord.CategoryChannel)
    guild = MagicMock()
    guild.get_channel.return_value = claimed
    channel = MagicMock(spec=discord.TextChannel)
    channel.guild = guild
    channel.edit = AsyncMock()

    _run(sync_order_category(channel=channel, order=_order(status=OrderStatus.CLAIMED, claimable=7), ctx=ctx))

    guild.get_channel.assert_called_once_with(ctx.channels.claimed_orders_category)
    channel.edit.assert_awaited_once_with(category=claimed, sync_permissions=True)


def test_sync_moves_channel_back_to_new_when_unclaimed() -> None:
    ctx = _ctx()
    new_cat = MagicMock(spec=discord.CategoryChannel)
    guild = MagicMock()
    guild.get_channel.return_value = new_cat
    channel = MagicMock(spec=discord.TextChannel)
    channel.guild = guild
    channel.edit = AsyncMock()

    _run(sync_order_category(channel=channel, order=_order(status=OrderStatus.NEW, claimable=10), ctx=ctx))

    guild.get_channel.assert_called_once_with(ctx.channels.new_orders_category)
    channel.edit.assert_awaited_once_with(category=new_cat, sync_permissions=True)


def test_sync_skips_edit_when_id_is_not_a_category() -> None:
    ctx = _ctx()
    guild = MagicMock()
    guild.get_channel.return_value = MagicMock(spec=discord.TextChannel)
    channel = MagicMock(spec=discord.TextChannel)
    channel.guild = guild
    channel.edit = AsyncMock()

    _run(sync_order_category(channel=channel, order=_order(status=OrderStatus.CLAIMED, claimable=7), ctx=ctx))

    channel.edit.assert_not_called()


def test_finished_worker_income_moves_to_completed() -> None:
    ctx = _ctx()
    completed = MagicMock(spec=discord.CategoryChannel)
    guild = MagicMock()
    guild.get_member.return_value = None
    guild.get_channel.side_effect = lambda cid: completed if cid == ctx.channels.completed_orders_category else MagicMock()
    channel = MagicMock(spec=discord.TextChannel)
    channel.edit = AsyncMock()
    channel.send = AsyncMock()
    order = _order(status=OrderStatus.COMPLETED, claimable=0)
    order["customer_id"] = "2"
    order["order_claims"]["order_completed"] = 10

    with (
        patch("bot.handlers.order_presenters.ItemService") as items_cls,
        patch("bot.handlers.order_presenters.refresh_order_embed", new_callable=AsyncMock),
        patch("bot.handlers.order_presenters.post_transaction_embed", new_callable=AsyncMock),
        patch("bot.handlers.order_presenters.WorkerRatingService"),
    ):
        items_cls.return_value.get_item_emoji = AsyncMock(return_value="x")
        _run(
            after_income_recorded(
                guild=guild,
                order_channel=channel,
                order=order,
                target="worker",
                user_id="1",
                quantity=10,
                result={"finished": True},
                ctx=ctx,
            )
        )

    channel.edit.assert_awaited_once_with(category=completed, sync_permissions=True)


def test_customer_income_does_not_move_to_completed() -> None:
    ctx = _ctx()
    guild = MagicMock()
    guild.get_member.return_value = None
    channel = MagicMock(spec=discord.TextChannel)
    channel.edit = AsyncMock()
    channel.send = AsyncMock()

    with (
        patch("bot.handlers.order_presenters.ItemService") as items_cls,
        patch("bot.handlers.order_presenters.refresh_order_embed", new_callable=AsyncMock),
        patch("bot.handlers.order_presenters.post_transaction_embed", new_callable=AsyncMock),
        patch("bot.handlers.order_presenters.WorkerRatingService"),
        patch("bot.handlers.order_presenters.close_embed", return_value=MagicMock()),
    ):
        items_cls.return_value.get_item_emoji = AsyncMock(return_value="x")
        _run(
            after_income_recorded(
                guild=guild,
                order_channel=channel,
                order=_order(status=OrderStatus.DELIVERED, claimable=0),
                target="customer",
                user_id="2",
                quantity=10,
                result={"delivered": True},
                ctx=ctx,
            )
        )

    channel.edit.assert_not_called()


def _claim_interaction(user_id: int = 11):
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 99
    channel.name = "ord-iron"
    guild = MagicMock()
    guild.get_channel.return_value = None
    interaction = MagicMock()
    interaction.user = member
    interaction.channel = channel
    interaction.guild = guild
    return interaction


def test_claim_handler_syncs_category_after_claim() -> None:
    ctx = _ctx()
    interaction = _claim_interaction()
    existing = sample_order(customer_id="c1")
    updated = _order(status=OrderStatus.CLAIMED, claimable=7)
    updated["item_name"] = "Iron Ore"
    handler = OrderHandler()

    with (
        patch("bot.handlers.orders.safe_defer", new_callable=AsyncMock),
        patch("bot.handlers.orders.safe_respond", new_callable=AsyncMock),
        patch("bot.handlers.orders.require_context", return_value=ctx),
        patch("bot.handlers.orders.has_role", return_value=True),
        patch("bot.handlers.orders.OrderService") as order_cls,
        patch("bot.handlers.orders.OrderClaimService") as claim_cls,
        patch("bot.handlers.orders.ItemService"),
        patch("bot.handlers.orders.sync_order_category", new_callable=AsyncMock) as sync,
        patch("bot.handlers.orders.refresh_order_embed", new_callable=AsyncMock),
        patch("bot.handlers.orders.log_activity", new_callable=AsyncMock),
    ):
        order_cls.return_value.get_by_channel_id = AsyncMock(return_value=existing)
        claim_cls.return_value.claim = AsyncMock(return_value=updated)
        _run(handler.handle_claim_action(interaction, action="claim", quantity=3))

    sync.assert_awaited_once_with(channel=interaction.channel, order=updated, ctx=ctx)
    claim_cls.return_value.claim.assert_awaited_once()


def test_claim_handler_rejects_own_order_without_sync() -> None:
    ctx = _ctx()
    interaction = _claim_interaction(user_id=99)
    existing = sample_order(customer_id="99")
    handler = OrderHandler()

    with (
        patch("bot.handlers.orders.safe_defer", new_callable=AsyncMock),
        patch("bot.handlers.orders.safe_respond", new_callable=AsyncMock) as respond,
        patch("bot.handlers.orders.require_context", return_value=ctx),
        patch("bot.handlers.orders.has_role", return_value=True),
        patch("bot.handlers.orders.OrderService") as order_cls,
        patch("bot.handlers.orders.OrderClaimService") as claim_cls,
        patch("bot.handlers.orders.sync_order_category", new_callable=AsyncMock) as sync,
    ):
        order_cls.return_value.get_by_channel_id = AsyncMock(return_value=existing)
        _run(handler.handle_claim_action(interaction, action="claim", quantity=1))

    claim_cls.return_value.claim.assert_not_called()
    sync.assert_not_called()
    assert "cannot claim your own order" in respond.call_args.kwargs.get("content", "").lower()
