from __future__ import annotations

from typing import Any


class AppError(Exception):
    """애플리케이션 공통 예외."""

    _default_user_message = "오류가 발생했습니다. 잠시 후 다시 시도해주세요."

    def __init__(
        self,
        message: str,
        user_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.user_message = user_message or self._default_user_message
        self.details = details or {}


class SpreadsheetError(AppError):
    """스프레드시트 작업 실패."""

    _default_user_message = "스프레드시트 저장 중 오류가 발생했습니다."


class SlackError(AppError):
    """Slack API 작업 실패."""

    _default_user_message = "슬랙 메시지 처리 중 오류가 발생했습니다."


class ValidationError(AppError):
    """입력값 검증 또는 권한 체크 실패."""

    _default_user_message = "입력값이 올바르지 않습니다."
