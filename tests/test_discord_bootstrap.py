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
from bot.ui.staff import (
    CID_ANNOUNCE,
    CID_BOOST,
    CID_CONTENT,
    CID_CUSTOMER,
    CID_GIVEAWAY,
    CID_METEOR,
    CID_WORKER,
    RoleClaimView,
    role_claim_embed,
)
from core.tenant import all_contexts, load_all_tenants
from core.bot import COA_ONLY_COMMANDS, EXTENSIONS, apply_guild_command_scope
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
            CID_BOOST,
            CID_METEOR,
        }
        assert CID_BOOST == "sl_rc:boost"
        assert CID_METEOR == "sl_rc:meteor"
        rows = {child.custom_id: child.row for child in RoleClaimView().children}
        assert rows == {
            CID_WORKER: 0,
            CID_CUSTOMER: 0,
            CID_ANNOUNCE: 0,
            CID_GIVEAWAY: 0,
            CID_CONTENT: 0,
            CID_BOOST: 1,
            CID_METEOR: 1,
        }

    _run(body())


def test_role_claim_adds_boost_and_meteor_after_content_for_coa() -> None:
    load_all_tenants()
    games = {ctx.game: ctx for ctx in all_contexts()}
    coa = role_claim_embed(games["coa"])
    eop = role_claim_embed(games["eop"])
    assert "### 🔔 Content" in (coa.description or "")
    assert "### 🚀 Boost" in (coa.description or "")
    assert "### ☄️ Meteor" in (coa.description or "")
    assert (coa.description or "").index("Content") < (coa.description or "").index("Boost")
    assert (coa.description or "").index("Boost") < (coa.description or "").index("Meteor")
    assert "### 🚀 Boost" not in (eop.description or "")
    assert "### ☄️ Meteor" not in (eop.description or "")

    async def body() -> None:
        coa_ids = _child_ids(RoleClaimView.for_context(games["coa"]))
        eop_ids = _child_ids(RoleClaimView.for_context(games["eop"]))
        assert CID_BOOST in coa_ids and CID_METEOR in coa_ids
        assert CID_BOOST not in eop_ids and CID_METEOR not in eop_ids

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


def test_eop_drops_coa_only_slash_commands() -> None:
    tree = MagicMock()
    coa = MagicMock(guild_id=1, game="coa")
    eop = MagicMock(guild_id=2, game="eop")
    apply_guild_command_scope(tree, coa)
    tree.remove_command.assert_not_called()
    apply_guild_command_scope(tree, eop)
    assert "monster-grind" in COA_ONLY_COMMANDS
    assert tree.remove_command.call_args.args[0] == "monster-grind"


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
            patch("core.view_registry.start_coa_reminders", new_callable=AsyncMock) as reminders,
        ):
            await register_persistent_views(bot)
        reminders.assert_awaited_once_with(bot)

    asyncio.run(body())
    names = {type(call.args[0]).__name__ for call in bot.add_view.call_args_list}
    assert {"OrderClaimView", "OrderCloseView", "RatingWorkerButton", "RoleClaimView"} <= names
    community.register_persistent_views.assert_awaited_once_with(bot)
