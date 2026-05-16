from __future__ import annotations

import random


class CountingService:
    def generate(self) -> tuple[str, int]:
        a = random.randint(1, 100)
        b = random.randint(1, 100)

        op = random.choice(
            ["+", "-", "*", "/"]
        )

        if op == "/":
            a *= b

        question = f"{a} {op} {b}"

        if op == "+":
            answer = a + b

        elif op == "-":
            answer = a - b

        elif op == "*":
            answer = a * b

        else:
            answer = a // b

        return question, answer