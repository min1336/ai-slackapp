"""Core application utilities.

Provides logging configuration for the application.
"""

from __future__ import annotations

from app.core.logger import get_logger, setup_logging

__all__ = [
    "get_logger",
    "setup_logging",
]
