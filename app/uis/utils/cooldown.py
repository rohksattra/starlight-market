# utils/cooldown.py
from time import time

_COOLDOWN: dict[tuple[int, str], float] = {}

def check_cooldown(*, user_id: int, key: str, seconds: int) -> None:
    now = time()
    k = (user_id, key)
    last = _COOLDOWN.get(k, 0)
    if now - last < seconds:
        raise ValueError(f"Cooldown {seconds}s. Please wait.")
    _COOLDOWN[k] = now
