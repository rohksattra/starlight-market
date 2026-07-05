from __future__ import annotations

import logging
from typing import Awaitable, Callable, TypeVar

from pymongo import ReadPreference
from pymongo.errors import OperationFailure

from db.mongo import get_client


log = logging.getLogger("db.mongo_transaction")

T = TypeVar("T")


async def run_transaction(fn: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
    client = get_client()
    async with await client.start_session() as session:
        try:
            async with session.start_transaction(read_preference=ReadPreference.PRIMARY):
                return await fn(session, *args, **kwargs)
        except OperationFailure as exc:
            if exc.has_error_label("TransientTransactionError"):
                log.warning("Mongo transaction retry needed: %s", exc)
            raise
