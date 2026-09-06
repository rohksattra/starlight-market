from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

from pymongo import ReadPreference
from pymongo.errors import ConnectionFailure, OperationFailure, PyMongoError

from database.connection import get_client

log = logging.getLogger("database.transactions")

T = TypeVar("T")
_MAX_ATTEMPTS = 3
_RETRY_LABELS = frozenset({"TransientTransactionError", "UnknownTransactionCommitResult"})


def _is_retryable(exc: BaseException) -> bool:
    checker = getattr(exc, "has_error_label", None)
    if not callable(checker):
        return False
    return any(checker(label) for label in _RETRY_LABELS)


async def run_transaction(fn: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
    client = get_client()
    async with await client.start_session() as session:
        last_exc: BaseException | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                async with session.start_transaction(read_preference=ReadPreference.PRIMARY):
                    return await fn(session, *args, **kwargs)
            except (ConnectionFailure, OperationFailure, PyMongoError) as exc:
                last_exc = exc
                if not _is_retryable(exc) or attempt >= _MAX_ATTEMPTS:
                    raise
                log.warning(
                    "Mongo transaction retry %s/%s: %s",
                    attempt,
                    _MAX_ATTEMPTS,
                    exc,
                )
                await asyncio.sleep(0.05 * attempt)
        assert last_exc is not None
        raise last_exc
