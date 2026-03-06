from __future__ import annotations

import logging

import structlog

from app.config import get_env_config


def get_log_level() -> int:
    return logging.DEBUG if get_env_config().is_dev else logging.INFO


def setup_logging() -> None:
    is_dev = get_env_config().is_dev
    level = get_log_level()

    # stdlib 로깅 — 외부 라이브러리는 WARNING 이상만 출력
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

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
