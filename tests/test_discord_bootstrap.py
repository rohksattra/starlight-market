from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from bot.ui.community import (
    giveaway_custom_cancel,
    giveaway_custom_claim,
    giveaway_custom_close,
    giveaway_custom_join,
    giveaway_custom_participants,
    giveaway_custom_refresh,
    giveaway_custom_reroll_all,
    giveaway_custom_reroll_partial,
)
from bot.ui.order_views import CLOSE_ORDER_CUSTOM_ID, OrderClaimView, OrderCloseView, RatingWorkerButton
from bot.ui.staff import CID_ANNOUNCE, CID_CONTENT, CID_CUSTOMER, CID_GIVEAWAY, CID_WORKER, RoleClaimView
from core.bot import EXTENSIONS
from core.view_registry import register_game_persistent_views, register_persistent_views


def _child_ids(view) -> set[str]:
    return {getattr(child, "custom_id", "") for child in view.children}


def _run(coro):
    return asyncio.run(coro)


def test_order_claim_view_custom_ids_are_stable() -> None:
    async def body() -> None:
        assert _child_ids(OrderClaimView()) == {
            "orderclaim:claim",
            "orderclaim:unclaim",
            "orderclaim:refresh",
        }

    _run(body())


def test_order_close_and_rating_custom_ids_are_stable() -> None:
    async def body() -> None:
        assert _child_ids(OrderCloseView()) == {CLOSE_ORDER_CUSTOM_ID}
        assert CLOSE_ORDER_CUSTOM_ID == "orderclose:close"
        assert _child_ids(RatingWorkerButton()) == {
            "rating:worker:1",
            "rating:worker:2",
            "rating:worker:3",
            "rating:worker:4",
            "rating:worker:5",
        }

    _run(body())


def test_role_claim_custom_ids_are_stable() -> None:
    async def body() -> None:
        assert _child_ids(RoleClaimView()) == {
            CID_WORKER,
            CID_CUSTOMER,
            CID_ANNOUNCE,
            CID_GIVEAWAY,
            CID_CONTENT,
        }

    _run(body())


def test_giveaway_custom_id_contract() -> None:
    assert giveaway_custom_join("g1") == "sl_gv:g1:j"
    assert giveaway_custom_participants("g1") == "sl_gv:g1:p"
    assert giveaway_custom_refresh("g1") == "sl_gv:g1:r"
    assert giveaway_custom_cancel("g1") == "sl_gv:g1:c"
    assert giveaway_custom_reroll_all("g1") == "sl_gvw:g1:ra"
    assert giveaway_custom_reroll_partial("g1") == "sl_gvw:g1:rp"
    assert giveaway_custom_claim("g1") == "sl_gvw:g1:cl"
    assert giveaway_custom_close("g1") == "sl_gvw:g1:x"


def test_bot_loads_command_extensions() -> None:
    assert EXTENSIONS == (
        "bot.events.members",
        "bot.events.messages",
        "bot.events.activity",
        "bot.commands.orders",
        "bot.commands.market",
        "bot.commands.staff",
        "bot.commands.community",
    )


def test_game_persistent_views_are_registered() -> None:
    bot = MagicMock()

    async def body() -> None:
        register_game_persistent_views(bot)

    _run(body())
    names = [type(call.args[0]).__name__ for call in bot.add_view.call_args_list]
    assert names.count("CountingGameView") == 1
    assert names.count("WordChainGameView") == 1
    assert names.count("ScrambleGameView") == 1
    assert names.count("BattleGameView") == 2
    assert "GameLeaderboardPaginationView" in names


def test_persistent_views_include_order_and_role_panels() -> None:
    bot = MagicMock()
    community = MagicMock()
    community.register_persistent_views = AsyncMock()
    community.recover_stale_giveaways = AsyncMock()

    async def body() -> None:
        with (
            patch("core.view_registry.all_contexts", return_value=[]),
            patch("core.view_registry.recover_game_battle_timers", new_callable=AsyncMock),
            patch("core.view_registry.get_community_handler", return_value=community),
        ):
            await register_persistent_views(bot)

    asyncio.run(body())
    names = {type(call.args[0]).__name__ for call in bot.add_view.call_args_list}
    assert {"OrderClaimView", "OrderCloseView", "RatingWorkerButton", "RoleClaimView"} <= names
    community.register_persistent_views.assert_awaited_once_with(bot)
