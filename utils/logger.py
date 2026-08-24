"""Console logging setup for Starlight V2."""
from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-35s | %(message)s"
DATE_FORMAT = "%H:%M:%S"


def setup_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(handler)

    for name in ("discord", "discord.client", "discord.gateway", "discord.http"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.WARNING if name == "discord.http" else logging.INFO)
        logger.addHandler(handler)
