from __future__ import annotations

import logging
import os


def get_log_level() -> int:
    """dev=DEBUG, prod=INFO"""
    env = os.getenv("ENVIRONMENT", "dev").lower()
    return logging.DEBUG if env == "dev" else logging.INFO


def setup_logging(env: str | None = None) -> None:
    if env:
        os.environ["ENVIRONMENT"] = env

    logging.basicConfig(
        level=get_log_level(),
        format="%(asctime)s - %(name)s - [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logging.getLogger("slack_bolt").setLevel(logging.WARNING)
    logging.getLogger("slack_sdk").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
