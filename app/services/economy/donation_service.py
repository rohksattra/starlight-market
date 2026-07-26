from __future__ import annotations

from typing import Any

from app.repositories.user_repo import UserRepository


class DonationService:
    def __init__(self) -> None:
        self.users = UserRepository()

    async def record(self, *, user_id: str, gold: int) -> dict[str, Any]:
        await self.users.ensure_user(user_id)
        await self.users.inc_donation_given(user_id=user_id, amount=gold)
        return await self.users.get_user(user_id) or {}
