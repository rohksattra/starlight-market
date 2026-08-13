"""Register persistent Discord views."""
from __future__ import annotations

import logging

from discord.ext import commands

from bot.handlers.community import get_community_handler
from bot.handlers.games import get_game_handler
from bot.ui.games import (
    BattleGameView,
    CountingGameView,
    GameLeaderboardPaginationView,
    ScrambleGameView,
    WordChainGameView,
)
from bot.ui.market import (
    ClaimablePaginationView,
    LeaderboardPaginationView,
    MarketStatisticRefreshView,
    PricePaginationView,
    RatedLeaderboardPaginationView,
)
from bot.ui.orders import OrderClaimView, OrderCloseView, RatingWorkerButton
from bot.ui.staff import RoleClaimView
from core.tenant import all_contexts
from models.games import BATTLE_GAME_TYPES, LEADERBOARD_TYPES
from services.items import ItemService

log = logging.getLogger("core.view_registry")

_LB_TITLES = {
    "worker": "🏆 Top 100 Workers",
    "customer": "🏅 Top 100 Customers",
    "item": "🛒 Top 100 Items",
    "donor": "🎁 Top 100 Donors",
}


def register_game_persistent_views(bot: commands.Bot) -> None:
    bot.add_view(CountingGameView())
    bot.add_view(WordChainGameView())
    bot.add_view(ScrambleGameView())
    bot.add_view(BattleGameView(game_type="monster"))
    bot.add_view(BattleGameView(game_type="boss"))

    for game_type in LEADERBOARD_TYPES:
        bot.add_view(GameLeaderboardPaginationView(game_type=game_type))


async def recover_game_battle_timers(bot: commands.Bot) -> None:
    runtime = get_game_handler(bot).runtime
    for ctx in all_contexts():
        for game_type in BATTLE_GAME_TYPES:
            try:
                await runtime.recover_battle_auto_reset(ctx, game_type)
            except Exception:
                log.exception(
                    "Battle auto-reset recovery failed | game=%s db=%s type=%s",
                    ctx.game,
                    ctx.db_name,
                    game_type,
                )


async def register_persistent_views(bot: commands.Bot) -> None:
    categories: set[str] = set()
    for ctx in all_contexts():
        try:
            for category in await ItemService(ctx).list_categories():
                if category:
                    categories.add(str(category))
        except Exception:
            log.exception("Failed to load categories for price views | game=%s", ctx.game)

    for category in sorted(categories):
        bot.add_view(PricePaginationView(category=category))

    bot.add_view(ClaimablePaginationView())
    bot.add_view(MarketStatisticRefreshView())
    bot.add_view(RatedLeaderboardPaginationView())
    bot.add_view(OrderClaimView())
    bot.add_view(OrderCloseView())
    bot.add_view(RatingWorkerButton())
    bot.add_view(RoleClaimView())

    for lb_type, title in _LB_TITLES.items():
        bot.add_view(LeaderboardPaginationView(lb_type=lb_type, title=title))  # type: ignore[arg-type]

    register_game_persistent_views(bot)
    await recover_game_battle_timers(bot)

    community = get_community_handler()
    await community.register_persistent_views(bot)
    await community.recover_stale_giveaways(bot)

    log.info(
        "Persistent views registered | price_categories=%d role_claim=1 games=5",
        len(categories),
    )
