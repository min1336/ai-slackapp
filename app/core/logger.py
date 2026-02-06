from __future__ import annotations

import logging
import os

import structlog


def get_log_level() -> int:
    """dev=DEBUG, prod=INFO"""
    env = os.getenv("ENVIRONMENT", "dev").lower()
    return logging.DEBUG if env == "dev" else logging.INFO


def setup_logging(env: str | None = None) -> None:
    if env:
        os.environ["ENVIRONMENT"] = env

    is_dev = os.getenv("ENVIRONMENT", "dev").lower() == "dev"
    level = get_log_level()

    # stdlib 로깅 기본 설정 (Slack Bolt 등 외부 라이브러리용)
    logging.basicConfig(level=level, format="%(message)s")
    logging.getLogger("slack_bolt").setLevel(logging.WARNING)
    logging.getLogger("slack_sdk").setLevel(logging.WARNING)

    # structlog 설정
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # 개발: 컬러 콘솔, 프로덕션: JSON (exc_info 직렬화 필요)
    renderers: list[structlog.types.Processor] = (
        [structlog.dev.ConsoleRenderer()]
        if is_dev
        else [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
    )

    structlog.configure(
        processors=[*shared_processors, *renderers],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
