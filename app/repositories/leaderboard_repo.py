from __future__ import annotations

from typing import Any, Dict, List

from db.mongo import get_db


LeaderboardRow = Dict[str, Any]


class LeaderboardRepository:
    def __init__(self) -> None:
        db = get_db()
        self.users = db.users
        self.items = db.items

    async def top_workers(self, *, limit: int = 100) -> List[LeaderboardRow]:
        cursor = (
            self.users.find(
                {"total_worker_income": {"$gt": 0}},
                {"_id": 0, "user_id": 1, "total_worker_income": 1},
            )
            .sort("total_worker_income", -1)
            .limit(limit)
        )
        return [
            {"id": d["user_id"], "value": int(d["total_worker_income"])}
            async for d in cursor
        ]

    async def top_customers(self, *, limit: int = 100) -> List[LeaderboardRow]:
        cursor = (
            self.users.find(
                {"total_customer_spent": {"$gt": 0}},
                {"_id": 0, "user_id": 1, "total_customer_spent": 1},
            )
            .sort("total_customer_spent", -1)
            .limit(limit)
        )
        return [
            {"id": d["user_id"], "value": int(d["total_customer_spent"])}
            async for d in cursor
        ]

    async def top_donors(self, *, limit: int = 100) -> List[LeaderboardRow]:
        cursor = (
            self.users.find(
                {"donation_given": {"$gt": 0}},
                {"_id": 0, "user_id": 1, "donation_given": 1},
            )
            .sort("donation_given", -1)
            .limit(limit)
        )
        return [
            {"id": d["user_id"], "value": int(d["donation_given"])}
            async for d in cursor
        ]

    async def top_items(self, *, limit: int = 100) -> List[LeaderboardRow]:
        cursor = (
            self.items.find(
                {"item_sold": {"$gt": 0}},
                {
                    "_id": 0,
                    "item_id": 1,
                    "item_name": 1,
                    "item_sold": 1,
                },
            )
            .sort("item_sold", -1)
            .limit(limit)
        )
        return [
            {
                "item_id": d["item_id"],
                "name": d["item_name"],
                "value": int(d["item_sold"]),
            }
            async for d in cursor
        ]

    async def top_rated_workers(self, *, limit: int = 100, min_count: int = 1) -> List[LeaderboardRow]:
        pipeline = [
            {"$match": {"count_worker_rating": {"$gte": min_count}}},
            {
                "$project": {
                    "_id": 0,
                    "user_id": 1,
                    "count_worker_rating": 1,
                    "total_worker_star": 1,
                    "avg_rating": {
                        "$cond": [
                            {"$gt": ["$count_worker_rating", 0]},
                            {"$divide": ["$total_worker_star", "$count_worker_rating"]},
                            0,
                        ]
                    },
                }
            },
            {"$sort": {"avg_rating": -1, "count_worker_rating": -1}},
            {"$limit": limit},
        ]

        rows = []
        async for d in self.users.aggregate(pipeline):
            rows.append(
                {
                    "id": d["user_id"],
                    "avg": float(d.get("avg_rating", 0)),
                    "count": int(d.get("count_worker_rating", 0)),
                }
            )
        return rows

    async def top_counting_scores(self, *, limit: int = 100) -> List[LeaderboardRow]:
        cursor = (
            self.users.find(
                {"counting_score": {"$gt": 0}},
                {"_id": 0, "user_id": 1, "counting_score": 1},
            )
            .sort("counting_score", -1)
            .limit(limit)
        )
        return [
            {"id": d["user_id"], "value": int(d.get("counting_score", 0))}
            async for d in cursor
        ]