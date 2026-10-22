"""Mongo queries for per-game runtime settings (market fee, etc.)."""
from __future__ import annotations

from typing import Any, Optional

from core.time import utc_now
from database.connection import get_db

_MARKET_ID = "market"
Session = Any


class SettingRepo:
    def __init__(self, db_name: str) -> None:
        self.settings = get_db(db_name).settings

    def _session_kw(self, session: Session | None) -> dict:
        return {} if session is None else {"session": session}

    async def get_market(self) -> Optional[dict[str, Any]]:
        return await self.settings.find_one({"_id": _MARKET_ID}, {"_id": 0})

    async def set_market_fee_rate(
        self,
        *,
        fee_rate: float,
        updated_by: str,
        session: Session | None = None,
    ) -> None:
        now = utc_now()
        await self.settings.update_one(
            {"_id": _MARKET_ID},
            {
                "$set": {
                    "market_fee_rate": float(fee_rate),
                    "updated_by": str(updated_by),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
            **self._session_kw(session),
        )

    async def seed_market_fee_rate(
        self,
        *,
        fee_rate: float,
        session: Session | None = None,
    ) -> None:
        now = utc_now()
        await self.settings.update_one(
            {"_id": _MARKET_ID},
            {
                "$setOnInsert": {
                    "market_fee_rate": float(fee_rate),
                    "updated_by": None,
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
            **self._session_kw(session),
        )
