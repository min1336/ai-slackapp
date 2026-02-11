"""Slack view state 값 추출 순수 함수 테스트"""

from __future__ import annotations

from app.listener.payload import (
    extract_date_value,
    extract_select_value,
    extract_text_value,
)


class TestExtractTextValue:
    """extract_text_value() 함수 테스트"""

    def test_정상적인_값_추출(self):
        # Given - Slack 모달 values 구조
        values = {"block_booking_key": {"action_booking_key": {"value": "BOOK-123"}}}

        # When
        result = extract_text_value(values, "block_booking_key", "action_booking_key")

        # Then
        assert result == "BOOK-123"

    def test_block_id가_없으면_빈문자열_반환(self):
        values = {}
        result = extract_text_value(values, "nonexistent_block", "action_id")
        assert result == ""

    def test_action_id가_없으면_빈문자열_반환(self):
        values = {"block_id": {}}
        result = extract_text_value(values, "block_id", "nonexistent_action")
        assert result == ""

    def test_value가_None이면_빈문자열_반환(self):
        values = {"block_id": {"action_id": {"value": None}}}
        result = extract_text_value(values, "block_id", "action_id")
        assert result == ""

    def test_value키가_없으면_빈문자열_반환(self):
        values = {"block_id": {"action_id": {}}}
        result = extract_text_value(values, "block_id", "action_id")
        assert result == ""


class TestExtractDateValue:
    """extract_date_value() 함수 테스트"""

    def test_정상적인_날짜_추출(self):
        # Given - Slack date picker values 구조
        values = {"block_date": {"action_date": {"selected_date": "2024-01-15"}}}

        # When
        result = extract_date_value(values, "block_date", "action_date")

        # Then
        assert result == "2024-01-15"

    def test_block_id가_없으면_빈문자열_반환(self):
        values = {}
        result = extract_date_value(values, "nonexistent", "action")
        assert result == ""

    def test_selected_date가_None이면_빈문자열_반환(self):
        values = {"block_id": {"action_id": {"selected_date": None}}}
        result = extract_date_value(values, "block_id", "action_id")
        assert result == ""


class TestExtractSelectText:
    """extract_select_value() 함수 테스트"""

    def test_정상적인_선택값_추출(self):
        # Given - Slack static_select values 구조
        values = {
            "block_issue": {
                "action_issue": {
                    "selected_option": {
                        "text": {"text": "결제 오류"},
                        "value": "payment_error",
                    }
                }
            }
        }

        # When
        result = extract_select_value(values, "block_issue", "action_issue")

        # Then
        assert result == "결제 오류"

    def test_block_id가_없으면_빈문자열_반환(self):
        values = {}
        result = extract_select_value(values, "nonexistent", "action")
        assert result == ""

    def test_selected_option이_None이면_빈문자열_반환(self):
        values = {"block_id": {"action_id": {"selected_option": None}}}
        result = extract_select_value(values, "block_id", "action_id")
        assert result == ""

    def test_selected_option이_빈딕셔너리면_빈문자열_반환(self):
        values = {"block_id": {"action_id": {"selected_option": {}}}}
        result = extract_select_value(values, "block_id", "action_id")
        assert result == ""

    def test_text_중첩구조에서_정상_추출(self):
        # Slack의 실제 구조: selected_option.text.text
        values = {
            "block": {
                "action": {
                    "selected_option": {
                        "text": {"type": "plain_text", "text": "옵션A"},
                        "value": "option_a",
                    }
                }
            }
        }
        result = extract_select_value(values, "block", "action")
        assert result == "옵션A"
