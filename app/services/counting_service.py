# app/services/counting_service.py
from __future__ import annotations

import random


class CountingService:
    def generate(self) -> tuple[str, int]:
        a = random.randint(1, 100)
        b = random.randint(1, 100)
        op = random.choice(["+", "-", "*", "/"])
        if op == "/":
            a = a * b
        question = f"{a} {op} {b}"
        answer = int(eval(question))
        return question, answer
