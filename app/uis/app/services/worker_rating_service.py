# app/services/worker_rating_service.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import uuid4

from app.repositories.worker_rating_repo import WorkerRatingRepository
from app.repositories.worker_repo import WorkerRepository


log = logging.getLogger("services.worker_rating_service")


class WorkerRatingService:
    def __init__(self) -> None:
        self.worker_ratings = WorkerRatingRepository()
        self.workers = WorkerRepository()

    async def request_rating(self, *, transaction_id: str, worker_id: str, customer_id: str, expire_days: int = 3) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        rating = {
            "worker_rating_id": str(uuid4()),
            "transaction_id": transaction_id,
            "worker_id": worker_id,
            "customer_id": customer_id,
            "created_at": now,
            "expired_at": now + timedelta(days=expire_days),
            "rated": False,
        }
        await self.worker_ratings.create_rating(rating)
        log.info("Worker rating requested | transaction=%s worker=%s customer=%s", transaction_id, worker_id, customer_id)
        return rating

    async def submit_rating(self, *, transaction_id: str, customer_id: str, rating: int) -> None:
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5")
        record = await self.worker_ratings.get_by_transaction(transaction_id)
        if not record:
            raise ValueError("Rating request not found")
        if record["customer_id"] != customer_id:
            log.warning("Rating denied | not owner | transaction=%s user=%s", transaction_id, customer_id)
            raise PermissionError("You are not allowed to rate this worker")
        now = datetime.now(timezone.utc)
        expired_at = record["expired_at"]
        if expired_at.tzinfo is None:
            expired_at = expired_at.replace(tzinfo=timezone.utc)
        if expired_at < now:
            log.info("Worker rating expired | transaction=%s", transaction_id)
            raise ValueError("Rating request expired")
        if record.get("rated"):
            raise ValueError("Rating already submitted")
        ok = await self.worker_ratings.rating_submit(transaction_id=transaction_id, rating=rating, rated_at=now)
        if not ok:
            raise RuntimeError("Failed to submit rating")
        worker_id = record["worker_id"]
        await self.workers.ensure_worker(worker_id)
        await self.workers.inc_worker_rating(worker_id=worker_id, rating=rating)
        log.info("Worker rated | transaction=%s worker=%s rating=%s", transaction_id, worker_id, rating)
