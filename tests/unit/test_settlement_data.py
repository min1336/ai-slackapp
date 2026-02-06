"""SettlementData Pydantic 모델 테스트"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.models.settlement import SettlementData


class TestSettlementDataSerialization:
    """SettlementData JSON 직렬화 테스트"""

    def test_JSON_직렬화_역직렬화_round_trip(self):
        # Given
        original = SettlementData(
            user_name="테스터",
            booking_key="TEST-001",
            company_name="테스트업체",
            customer_name="홍길동",
            settlement_day="2024-01-15",
            issue_type="결제 오류",
            settlement_cost=100000,
            company_sub_name="서브업체",
            carmore_cost=5000,
            user_refund_cost=3000,
            seller_channel="직접판매",
            description="테스트 설명",
            requester_id="U123",
        )

        # When
        json_str = original.model_dump_json()
        restored = SettlementData.model_validate_json(json_str)

        # Then
        assert restored == original

    def test_필수_필드_누락시_ValidationError_발생(self):
        # When & Then
        with pytest.raises(ValidationError):
            SettlementData()

    def test_모든_필드가_있는_경우_직렬화(self, sample_settlement_data):
        # When
        json_str = sample_settlement_data.model_dump_json()
        parsed = json.loads(json_str)

        # Then
        assert parsed["user_name"] == "테스터"
        assert parsed["booking_key"] == "TEST-001"
        assert parsed["company_name"] == "테스트업체"
        assert parsed["customer_name"] == "홍길동"
        assert parsed["settlement_day"] == "2024-01-15"
        assert parsed["issue_type"] == "결제 오류"
        assert parsed["settlement_cost"] == 100000

    def test_Slack_버튼_value로_사용시_정상_동작(self):
        """Slack 버튼의 value 필드는 JSON 문자열이어야 함"""
        # Given
        data = SettlementData(
            user_name="테스터",
            booking_key="BOOK-123",
            company_name="A업체",
            customer_name="김철수",
            settlement_day="2024-02-01",
            issue_type="환불",
            settlement_cost=50000,
            requester_id="U123",
        )

        # When - Slack 버튼 value로 변환
        button_value = data.model_dump_json()

        # Then - 다시 역직렬화 가능해야 함
        restored = SettlementData.model_validate_json(button_value)
        assert restored.booking_key == "BOOK-123"
        assert restored.customer_name == "김철수"


class TestSettlementDataCostValidator:
    """금액 필드 자동 변환 테스트"""

    def test_문자열_금액을_정수로_변환한다(self):
        data = SettlementData(
            user_name="테스터",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            settlement_day="2024-01-01",
            issue_type="이슈",
            settlement_cost="100000",
            requester_id="U123",
        )
        assert data.settlement_cost == 100000

    def test_콤마_포함_금액을_변환한다(self):
        data = SettlementData(
            user_name="테스터",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            settlement_day="2024-01-01",
            issue_type="이슈",
            settlement_cost="1,000,000",
            requester_id="U123",
        )
        assert data.settlement_cost == 1000000

    def test_원_단위_포함_금액을_변환한다(self):
        data = SettlementData(
            user_name="테스터",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            settlement_day="2024-01-01",
            issue_type="이슈",
            carmore_cost="50,000원",
            requester_id="U123",
        )
        assert data.carmore_cost == 50000

    def test_빈_문자열은_None이_된다(self):
        data = SettlementData(
            user_name="테스터",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            settlement_day="2024-01-01",
            issue_type="이슈",
            settlement_cost="",
            requester_id="U123",
        )
        assert data.settlement_cost is None

    def test_None은_None_그대로_유지한다(self):
        data = SettlementData(
            user_name="테스터",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            settlement_day="2024-01-01",
            issue_type="이슈",
            requester_id="U123",
        )
        assert data.settlement_cost is None
        assert data.carmore_cost is None
        assert data.user_refund_cost is None

    def test_정수값은_그대로_유지한다(self):
        data = SettlementData(
            user_name="테스터",
            booking_key="BK-1",
            company_name="업체",
            customer_name="고객",
            settlement_day="2024-01-01",
            issue_type="이슈",
            settlement_cost=42000,
            requester_id="U123",
        )
        assert data.settlement_cost == 42000
