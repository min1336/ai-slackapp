from __future__ import annotations

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

import structlog

from app.config import get_env_config


def get_log_level() -> int:
    return logging.DEBUG if get_env_config().is_dev else logging.INFO


def _create_json_formatter() -> structlog.stdlib.ProcessorFormatter:
    """JSON 포맷터 — 프로덕션 stdout/파일용."""
    return structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )


def _create_console_formatter() -> structlog.stdlib.ProcessorFormatter:
    """컬러 콘솔 포맷터 — 개발 환경용."""
    return structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(),
        ],
    )


def setup_logging() -> None:
    is_dev = get_env_config().is_dev
    level = get_log_level()
    log_dir = os.getenv("LOG_DIR", "")

    # structlog 프로세서 체인 (포맷팅은 ProcessorFormatter가 담당)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # stdlib 루트 로거 — 기존 핸들러 제거 후 재설정
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    # 1) stdout 핸들러 (항상 활성 — docker logs 호환)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(
        _create_console_formatter() if is_dev else _create_json_formatter()
    )
    root_logger.addHandler(stdout_handler)

    # 2) 파일 핸들러 (LOG_DIR 설정 시만 활성 — 일별 롤링, 30일 보관)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            filename=os.path.join(log_dir, "bot.log"),
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setFormatter(_create_json_formatter())
        root_logger.addHandler(file_handler)

    # 외부 라이브러리 노이즈 억제
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
