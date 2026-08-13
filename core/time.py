"""UTC clock. Drop-in for deprecated datetime.utcnow()."""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Naive UTC now — matches Motor's decoded BSON dates."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
