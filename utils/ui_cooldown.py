from __future__ import annotations

import time
from typing import Dict


def begin_refresh_cooldown(
    cooldowns: Dict[int, float],
    user_id: int,
    *,
    seconds: int,
) -> int | None:
    """Return remaining seconds if on cooldown; otherwise record use and return None."""
    now = time.time()
    last_used = cooldowns.get(user_id)
    if last_used is not None:
        remaining = seconds - (now - last_used)
        if remaining > 0:
            return int(remaining)
    cooldowns[user_id] = now
    return None


def clear_refresh_cooldown(cooldowns: Dict[int, float], user_id: int) -> None:
    cooldowns.pop(user_id, None)
