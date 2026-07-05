from __future__ import annotations

from app.services.claimable_service import ClaimableService


class ClaimableHandler:
    def __init__(self) -> None:
        self.service = ClaimableService()

    async def fetch_claimable(self) -> list[dict]:
        return await self.service.list_claimable()


_handler: ClaimableHandler | None = None


def get_claimable_handler() -> ClaimableHandler:
    global _handler
    if _handler is None:
        _handler = ClaimableHandler()
    return _handler
