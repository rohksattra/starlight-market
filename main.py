# main.py
from utils.logger import setup_logging

setup_logging()

from core.bot import run_bot


if __name__ == "__main__":
    run_bot()