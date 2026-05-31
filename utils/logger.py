# utils/logger.py
from __future__ import annotations

import logging
import sys


LOG_FORMAT = (
    "%(asctime)s | "
    "%(levelname)-8s | "
    "%(name)-35s | "
    "%(message)s"
)

DATE_FORMAT = "%H:%M:%S"


class EmojiLevelFilter(logging.Filter):
    LEVEL_EMOJI = {"DEBUG": "🐞", "INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "🔥", "CRITICAL": "💥"}

    def filter(self, record: logging.LogRecord) -> bool:
        emoji = self.LEVEL_EMOJI.get(record.levelname)
        if emoji and not record.msg.startswith(tuple(self.LEVEL_EMOJI.values())):
            record.msg = f"{emoji}  {record.msg}"
        return True


def setup_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    handler.addFilter(EmojiLevelFilter())
    root.addHandler(handler)
    for name in ("discord", "discord.client", "discord.gateway", "discord.http"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.WARNING if name == "discord.http" else logging.INFO)
        logger.addHandler(handler)
