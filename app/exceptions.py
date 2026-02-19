from __future__ import annotations

from typing import Any


class AppError(Exception):
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
    _default_user_message = "스프레드시트 저장 중 오류가 발생했습니다."


class SlackError(AppError):
    _default_user_message = "슬랙 메시지 처리 중 오류가 발생했습니다."


class ValidationError(AppError):
    _default_user_message = "입력값이 올바르지 않습니다."


class AlreadyProcessedError(AppError):
    _default_user_message = "이미 처리된 건입니다."


class SettlementCompletedError(AlreadyProcessedError):
    _default_user_message = "이미 정산완료된 건입니다."


class DatabaseError(AppError):
    """데이터베이스 저장/조회 중 발생하는 오류."""

    _default_user_message = "데이터 저장 중 오류가 발생했습니다."
