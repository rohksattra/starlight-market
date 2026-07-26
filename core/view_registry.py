from __future__ import annotations

import logging

from discord.ext import commands

from app.domains.game_domain import LEADERBOARD_TYPES
from app.handlers.giveaway import get_giveaway_handler
from app.services.item_service import ItemService
from app.views.claimable_button import ClaimablePaginationView
from app.views.game_leaderboard_button import GameLeaderboardPaginationView
from app.views.game_view import (
    BattleGameView,
    CountingGameView,
    DailyGameView,
    GuessGameView,
    ReactionRushGameView,
    ScrambleGameView,
    TreasureGameView,
    WordChainGameView,
)
from app.views.leaderboard_button import LeaderboardPaginationView
from app.views.market_statistic_button import MarketStatisticRefreshView
from app.views.order_claim_view import OrderClaimView
from app.views.order_close_view import OrderCloseView
from app.views.price_button import PricePaginationView
from app.views.rated_leaderboard_button import RatedLeaderboardPaginationView
from app.views.role_claim_view import RoleClaimView
from app.views.worker_rating_button import RatingWorkerButton


log = logging.getLogger("core.view_registry")


def register_game_persistent_views(bot: commands.Bot) -> None:
    bot.add_view(CountingGameView())
    bot.add_view(WordChainGameView())
    bot.add_view(GuessGameView())
    bot.add_view(TreasureGameView())
    bot.add_view(ReactionRushGameView())
    bot.add_view(ScrambleGameView())
    bot.add_view(DailyGameView())
    bot.add_view(BattleGameView(game_type="monster"))
    bot.add_view(BattleGameView(game_type="boss"))

    for game_type in LEADERBOARD_TYPES:
        bot.add_view(GameLeaderboardPaginationView(game_type=game_type))


async def register_persistent_views(bot: commands.Bot) -> None:
    item_serv = ItemService()
    categories = await item_serv.list_categories()
    for category in categories:
        bot.add_view(PricePaginationView(category=category))

    bot.add_view(ClaimablePaginationView())
    bot.add_view(RatingWorkerButton())
    bot.add_view(MarketStatisticRefreshView())
    bot.add_view(RatedLeaderboardPaginationView())
    bot.add_view(OrderClaimView())
    bot.add_view(OrderCloseView())
    bot.add_view(RoleClaimView())

    bot.add_view(
        LeaderboardPaginationView(
            lb_type="worker",
            title="🏆 Top 100 Workers",
        )
    )
    bot.add_view(
        LeaderboardPaginationView(
            lb_type="customer",
            title="🏅 Top 100 Customers",
        )
    )
    bot.add_view(
        LeaderboardPaginationView(
            lb_type="item",
            title="🛒 Top 100 Items",
        )
    )
    bot.add_view(
        LeaderboardPaginationView(
            lb_type="donor",
            title="🎁 Top 100 Donors",
        )
    )

    register_game_persistent_views(bot)

    giveaway = get_giveaway_handler()
    await giveaway.register_persistent_views(bot)
    await giveaway.recover_stale_giveaways(bot)

    log.info("Persistent views registered.")
