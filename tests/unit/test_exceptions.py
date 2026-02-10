"""Exception hierarchy 테스트"""

from __future__ import annotations

from app.exceptions import (
    AlreadyProcessedError,
    AppError,
    DatabaseError,
    SlackError,
    SpreadsheetError,
    ValidationError,
)


class TestExceptionHierarchy:
    """Exception 상속 구조 테스트"""

    def test_all_exceptions_inherit_from_app_error(self):
        assert issubclass(SpreadsheetError, AppError)
        assert issubclass(SlackError, AppError)
        assert issubclass(ValidationError, AppError)
        assert issubclass(DatabaseError, AppError)
        assert issubclass(AlreadyProcessedError, AppError)

    def test_app_error_has_default_user_message(self):
        error = AppError("Internal error")
        assert error.user_message == "오류가 발생했습니다. 잠시 후 다시 시도해주세요."

    def test_spreadsheet_error_has_specific_user_message(self):
        error = SpreadsheetError("Failed to save")
        assert "스프레드시트" in error.user_message

    def test_slack_error_has_specific_user_message(self):
        error = SlackError("Failed to send")
        assert "슬랙" in error.user_message

    def test_validation_error_has_specific_user_message(self):
        error = ValidationError("Invalid input")
        assert "입력값" in error.user_message

    def test_database_error_has_specific_user_message(self):
        error = DatabaseError("DB connection failed")
        assert "데이터 저장" in error.user_message

    def test_already_processed_error_has_specific_user_message(self):
        error = AlreadyProcessedError("Already handled")
        assert "이미 처리" in error.user_message

    def test_custom_user_message_overrides_default(self):
        error = SpreadsheetError("Internal error", user_message="커스텀 메시지")
        assert error.user_message == "커스텀 메시지"

    def test_details_are_stored(self):
        error = SpreadsheetError("Failed", details={"sheet": "test", "row": 1})
        assert error.details["sheet"] == "test"
        assert error.details["row"] == 1

    def test_empty_details_returns_empty_dict(self):
        error = AppError("Error")
        assert error.details == {}

    def test_message_is_accessible(self):
        error = AppError("Test message")
        assert error.message == "Test message"
        assert str(error) == "Test message"
