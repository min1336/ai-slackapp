"""ModalMetadata Pydantic 모델 테스트"""

from __future__ import annotations

import json

from app.models.settlement import ModalMetadata


class TestModalMetadataSerialization:
    """ModalMetadata JSON 직렬화 테스트"""

    def test_JSON_직렬화_역직렬화_round_trip(self):
        # Given
        original = ModalMetadata(
            channel_id="C12345",
            thread_ts="1234567890.123456",
            message_ts="1234567890.654321",
            user_name="테스터",
            booking_key="BOOK-001",
            company_name="테스트업체",
            customer_name="홍길동",
        )

        # When
        json_str = original.model_dump_json()
        restored = ModalMetadata.model_validate_json(json_str)

        # Then
        assert restored == original

    def test_빈_필드도_직렬화_가능하다(self):
        # Given
        metadata = ModalMetadata()

        # When
        json_str = metadata.model_dump_json()
        parsed = json.loads(json_str)

        # Then
        assert parsed["channel_id"] == ""
        assert parsed["thread_ts"] == ""
        assert parsed["message_ts"] == ""

    def test_모든_필드가_있는_경우_직렬화(self):
        # Given
        metadata = ModalMetadata(
            channel_id="C12345",
            thread_ts="1234567890.123456",
            message_ts="1234567890.654321",
            user_name="테스터",
            booking_key="BOOK-001",
            company_name="테스트업체",
            customer_name="홍길동",
        )

        # When
        json_str = metadata.model_dump_json()
        parsed = json.loads(json_str)

        # Then
        assert parsed["channel_id"] == "C12345"
        assert parsed["thread_ts"] == "1234567890.123456"
        assert parsed["user_name"] == "테스터"
        assert parsed["booking_key"] == "BOOK-001"

    def test_Slack_모달_private_metadata로_사용시_정상_동작(self):
        """Slack 모달의 private_metadata 필드는 JSON 문자열이어야 함"""
        # Given
        metadata = ModalMetadata(
            channel_id="C12345",
            thread_ts="1234567890.123456",
            message_ts="",
            user_name="김철수",
            booking_key="RES-999",
            company_name="A렌터카",
            customer_name="이영희",
        )

        # When - Slack 모달 private_metadata로 변환
        private_metadata = metadata.model_dump_json()

        # Then - 다시 역직렬화 가능해야 함
        restored = ModalMetadata.model_validate_json(private_metadata)
        assert restored.channel_id == "C12345"
        assert restored.thread_ts == "1234567890.123456"
        assert restored.booking_key == "RES-999"
