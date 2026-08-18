from __future__ import annotations

from unittest.mock import patch

import utils.cooldown as cooldown
from utils.cooldown import begin_cooldown, check_cooldown


def setup_function() -> None:
    cooldown._COOLDOWN.clear()


def test_begin_cooldown_allows_then_blocks() -> None:
    with patch("utils.cooldown.time", return_value=1_000.0):
        assert begin_cooldown(user_id=1, key="game:monster:attack", seconds=10) is None
    with patch("utils.cooldown.time", return_value=1_004.0):
        assert begin_cooldown(user_id=1, key="game:monster:attack", seconds=10) == 6


def test_begin_cooldown_is_shared_across_instances() -> None:
    with patch("utils.cooldown.time", return_value=1_000.0):
        assert begin_cooldown(user_id=7, key="game:boss:attack", seconds=10) is None
    with patch("utils.cooldown.time", return_value=1_001.0):
        assert begin_cooldown(user_id=7, key="game:boss:attack", seconds=10) == 9


def test_check_cooldown_raises_while_blocked() -> None:
    with patch("utils.cooldown.time", return_value=1_000.0):
        check_cooldown(user_id=2, key="profile_me", seconds=5)
    with patch("utils.cooldown.time", return_value=1_002.0):
        try:
            check_cooldown(user_id=2, key="profile_me", seconds=5)
        except ValueError as exc:
            assert "Cooldown" in str(exc)
        else:
            raise AssertionError("expected ValueError")
