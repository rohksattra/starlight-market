from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from bot.handlers.reminders import start_coa_reminders
from bot.ui.reminders import meteor_reminder_embed, world_boost_embed
from core.tenant import all_contexts, load_all_tenants
from services.coa_reminders import (
    BoostTracker,
    CoAWorld,
    boost_end_at,
    format_boost_remaining,
    is_trackable_world,
    meteor_event_window,
    meteor_slot_key,
    next_meteor_reminder_at,
    parse_worlds,
)


def test_next_meteor_reminder_before_slot() -> None:
    now = datetime(2026, 9, 6, 12, 30, 0)
    when = next_meteor_reminder_at(now)
    assert when == datetime(2026, 9, 6, 12, 55, 0)
    start, end = meteor_event_window(when)
    assert start == datetime(2026, 9, 6, 13, 0, 0)
    assert end == datetime(2026, 9, 6, 13, 5, 0)


def test_next_meteor_reminder_uses_grace_then_skips_sent_slot() -> None:
    now = datetime(2026, 9, 6, 12, 55, 10)
    when = next_meteor_reminder_at(now)
    assert when == datetime(2026, 9, 6, 12, 55, 0)

    skipped = next_meteor_reminder_at(now, sent_slots={meteor_slot_key(when)})
    assert skipped == datetime(2026, 9, 6, 13, 55, 0)


def test_next_meteor_reminder_after_grace() -> None:
    now = datetime(2026, 9, 6, 12, 56, 0)
    assert next_meteor_reminder_at(now) == datetime(2026, 9, 6, 13, 55, 0)


def test_boost_end_at_and_trackable_worlds() -> None:
    now = datetime(2026, 9, 6, 12, 0, 0)
    assert boost_end_at(now, 1_200_000) == datetime(2026, 9, 6, 12, 20, 0)
    assert boost_end_at(now, 0) is None

    playable = CoAWorld(5, "World 5 (Asia)", "ASIA", 72, True, 1_200_000, False)
    qa = CoAWorld(200, "War Bear QA", "US", 0, True, 1_200_000, True)
    assert is_trackable_world(playable)
    assert not is_trackable_world(qa)


def test_format_boost_remaining_hours_and_minutes() -> None:
    assert format_boost_remaining(3_600_000) == "1 hour"
    assert format_boost_remaining(5_400_000) == "1 hour 30 minutes"
    assert format_boost_remaining(120_000) == "2 minutes"
    assert format_boost_remaining(60_000) == "1 minute"
    assert format_boost_remaining(30_000) == "less than 1 minute"
    assert format_boost_remaining(0) == ""


def test_parse_worlds_and_boost_tracker() -> None:
    worlds = parse_worlds(
        [
            {
                "id": 5,
                "name": "World 5 (Asia)",
                "region": "ASIA",
                "players": 72,
                "is_boosted": True,
                "boost_remaining": 3_600_000,
                "members_only": False,
            },
            {
                "id": 200,
                "name": "War Bear QA",
                "region": "US",
                "players": 0,
                "is_boosted": True,
                "boost_remaining": 99,
                "members_only": True,
            },
            {"id": 11, "name": "World 11 (US)", "is_boosted": False},
        ]
    )
    tracker = BoostTracker()
    start = datetime(2026, 9, 5, 19, 2, 0)
    assert tracker.consume(worlds, now=start) == []
    ids = {doc["world_id"] for doc in tracker.drain_upserts()}
    assert ids == {5, 11}

    boosted = parse_worlds(
        [
            {"id": 5, "name": "World 5 (Asia)", "is_boosted": True, "boost_remaining": 3_570_000},
            {"id": 11, "name": "World 11 (US)", "is_boosted": True, "boost_remaining": 1_800_000},
            {"id": 200, "name": "War Bear QA", "is_boosted": True, "boost_remaining": 99},
        ]
    )
    new_boosts = tracker.consume(boosted, now=start + timedelta(seconds=30))
    assert [world.world_id for world in new_boosts] == [11]

    ended = parse_worlds(
        [
            {"id": 5, "name": "World 5 (Asia)", "is_boosted": False},
            {"id": 11, "name": "World 11 (US)", "is_boosted": False},
        ]
    )
    assert tracker.consume(ended, now=start + timedelta(seconds=60)) == []
    again = parse_worlds(
        [{"id": 5, "name": "World 5 (Asia)", "is_boosted": True, "boost_remaining": 1_200_000}]
    )
    assert [world.world_id for world in tracker.consume(again, now=start + timedelta(hours=1))] == [5]


def _asia(remaining_ms: int) -> list:
    return parse_worlds(
        [{"id": 5, "name": "World 5 (Asia)", "is_boosted": True, "boost_remaining": remaining_ms}]
    )


def test_boost_tracker_notifies_back_to_back_same_world() -> None:
    tracker = BoostTracker()
    start = datetime(2026, 9, 5, 19, 2, 0)
    assert tracker.consume(_asia(3_600_000), now=start) == []
    assert tracker.consume(_asia(30_000), now=start + timedelta(seconds=3_570)) == []
    next_boost = tracker.consume(_asia(3_600_000), now=start + timedelta(hours=1))
    assert [world.world_id for world in next_boost] == [5]


def test_boost_tracker_notifies_shorter_followup_boost() -> None:
    tracker = BoostTracker()
    start = datetime(2026, 9, 5, 19, 2, 0)
    assert tracker.consume(_asia(3_600_000), now=start) == []
    assert tracker.consume(_asia(3_570_000), now=start + timedelta(seconds=30)) == []
    shorter = tracker.consume(_asia(1_200_000), now=start + timedelta(seconds=60))
    assert [world.world_id for world in shorter] == [5]


def test_boost_tracker_notifies_when_remaining_jumps_from_50s_to_20m() -> None:
    tracker = BoostTracker()
    start = datetime(2026, 9, 5, 19, 2, 0)
    assert tracker.consume(_asia(50_000), now=start) == []
    jumped = tracker.consume(_asia(1_200_000), now=start + timedelta(seconds=30))
    assert [world.world_id for world in jumped] == [5]


def test_boost_tracker_notifies_similar_duration_after_failed_polls() -> None:
    tracker = BoostTracker()
    start = datetime(2026, 9, 5, 19, 43, 0)
    assert tracker.consume(_asia(1_140_000), now=start) == []
    assert tracker.consume([]) == []
    assert tracker.consume([]) == []
    followup = tracker.consume(_asia(1_200_000), now=start + timedelta(seconds=90))
    assert [world.world_id for world in followup] == [5]


def test_boost_tracker_notifies_after_stored_end_timestamp() -> None:
    tracker = BoostTracker()
    start = datetime(2026, 9, 5, 19, 2, 0)
    assert tracker.consume(_asia(3_600_000), now=start) == []
    assert tracker.consume([]) == []
    later = tracker.consume(_asia(1_200_000), now=start + timedelta(hours=1, minutes=1))
    assert [world.world_id for world in later] == [5]


def test_boost_tracker_keeps_world_missing_from_poll() -> None:
    tracker = BoostTracker()
    start = datetime(2026, 9, 5, 19, 2, 0)
    both = parse_worlds(
        [
            {"id": 5, "name": "World 5 (Asia)", "is_boosted": True, "boost_remaining": 3_600_000},
            {"id": 11, "name": "World 11 (US)", "is_boosted": True, "boost_remaining": 3_600_000},
        ]
    )
    assert tracker.consume(both, now=start) == []
    only_five = parse_worlds(
        [{"id": 5, "name": "World 5 (Asia)", "is_boosted": True, "boost_remaining": 3_570_000}]
    )
    assert tracker.consume(only_five, now=start + timedelta(seconds=30)) == []
    eleven_back = parse_worlds(
        [
            {"id": 5, "name": "World 5 (Asia)", "is_boosted": True, "boost_remaining": 3_540_000},
            {"id": 11, "name": "World 11 (US)", "is_boosted": True, "boost_remaining": 3_540_000},
        ]
    )
    assert tracker.consume(eleven_back, now=start + timedelta(seconds=60)) == []


def test_boost_tracker_hydrate_survives_restart() -> None:
    start = datetime(2026, 9, 5, 19, 2, 0)
    primed = BoostTracker()
    assert primed.consume(_asia(3_600_000), now=start) == []
    docs = primed.drain_upserts()
    assert docs and docs[0]["world_id"] == 5

    restarted = BoostTracker()
    restarted.hydrate(docs)
    later = start + timedelta(hours=1, minutes=1)
    assert [world.world_id for world in restarted.consume(_asia(1_200_000), now=later)] == [5]

    same_session = BoostTracker()
    same_session.hydrate(docs)
    assert same_session.consume(_asia(3_000_000), now=start + timedelta(minutes=10)) == []


def test_boost_tracker_ignores_empty_fetch() -> None:
    tracker = BoostTracker()
    live = parse_worlds(
        [{"id": 5, "name": "World 5 (Asia)", "is_boosted": True, "boost_remaining": 3_600_000}]
    )
    assert tracker.consume(live) == []
    assert tracker.consume([]) == []
    assert tracker.consume(live) == []


def test_reminder_embeds_use_approved_copy() -> None:
    start = datetime(2026, 9, 6, 13, 0, 0)
    end = datetime(2026, 9, 6, 13, 5, 0)
    meteor = meteor_reminder_embed(event_start=start, event_end=end)
    assert meteor.title == "☄️ Meteor Incoming"
    assert "A meteor is dropping in" in (meteor.description or "")
    assert "Get ready and head to the crash site." in (meteor.description or "")
    assert meteor.footer.text and "Meteor Reminder" in meteor.footer.text

    world = CoAWorld(5, "World 5 (Asia)", "ASIA", 72, True, 5_400_000, False)
    boost = world_boost_embed(world=world, ends_at=datetime(2026, 9, 6, 13, 30, 0))
    assert boost.title == "🚀 World Boost Active"
    assert "A player just boosted **World 5 (Asia)**." in (boost.description or "")
    assert "+50% EXP" in (boost.description or "")
    assert "**Time left:** **1 hour 30 minutes**." in (boost.description or "")
    assert "Log in and start grinding." in (boost.description or "")
    assert boost.footer.text and "World Boost Reminder" in boost.footer.text


def test_coa_config_has_reminder_ids_eop_does_not() -> None:
    load_all_tenants()
    games = {ctx.game: ctx for ctx in all_contexts()}
    assert games["coa"].channels.meteor_reminder == 1545962525668147260
    assert games["coa"].channels.world_boost == 1545962461377593354
    assert games["coa"].channels.bot_command == 1367879603221430404
    assert games["coa"].roles.meteor == 1545964957617750066
    assert games["coa"].roles.world_boost == 1545963839001198684
    assert games["eop"].channels.meteor_reminder == 0
    assert games["eop"].channels.world_boost == 0
    assert games["eop"].channels.bot_command == 0
    assert games["eop"].roles.meteor == 0
    assert games["eop"].roles.world_boost == 0


def test_start_coa_reminders_skips_eop() -> None:
    bot = MagicMock()
    eop = MagicMock()
    eop.game = "eop"
    eop.guild_id = 2
    eop.channels.meteor_reminder = 1
    eop.channels.world_boost = 1

    async def body() -> None:
        with (
            patch("bot.handlers.reminders.all_contexts", return_value=[eop]),
            patch("bot.handlers.reminders.asyncio.create_task") as create,
        ):
            await start_coa_reminders(bot)
        create.assert_not_called()

    asyncio.run(body())


def _close_created_task(coro, **_kwargs):
    coro.close()
    return MagicMock()


def test_start_coa_reminders_starts_both_loops() -> None:
    bot = MagicMock()
    coa = MagicMock()
    coa.game = "coa"
    coa.guild_id = 1
    coa.channels.meteor_reminder = 10
    coa.channels.world_boost = 20

    async def body() -> None:
        with (
            patch("bot.handlers.reminders.all_contexts", return_value=[coa]),
            patch(
                "bot.handlers.reminders.asyncio.create_task",
                side_effect=_close_created_task,
            ) as create,
        ):
            await start_coa_reminders(bot)
        assert create.call_count == 2

    asyncio.run(body())
