"""Per-key asyncio locks for serializing user actions in one process."""
from __future__ import annotations

import asyncio
from collections.abc import Hashable


class KeyedLocks:
    def __init__(self) -> None:
        self._locks: dict[Hashable, asyncio.Lock] = {}

    def lock(self, key: Hashable) -> asyncio.Lock:
        existing = self._locks.get(key)
        if existing is None:
            existing = asyncio.Lock()
            self._locks[key] = existing
        return existing


user_action_locks = KeyedLocks()
