from time import time

_COOLDOWN: dict[tuple[int, str], float] = {}


def check_cooldown(*, user_id: int, key: str, seconds: int) -> None:
    remaining = begin_cooldown(user_id=user_id, key=key, seconds=seconds)
    if remaining is not None:
        raise ValueError(f"Cooldown {seconds}s. Please wait.")


def begin_cooldown(*, user_id: int, key: str, seconds: int) -> int | None:
    """Start a cooldown window. Returns remaining seconds if still blocked."""
    now = time()
    stamp = _COOLDOWN.get((user_id, key), 0.0)
    remaining = seconds - (now - stamp)
    if remaining > 0:
        return max(1, int(remaining))
    _COOLDOWN[(user_id, key)] = now
    return None
