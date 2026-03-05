from __future__ import annotations

import pytest

from app.models.settlement import SettlementData


class TestParseCostNegative:
    """parse_cost validator가 음수 부호를 보존하는지 검증한다."""

    @pytest.fixture
    def _base_fields(self) -> dict:
        return {
            "user_name": "테스트",
            "booking_key": "ABC123",
            "company_name": "테스트업체",
            "customer_name": "홍길동",
            "issue_type": "환불",
            "settlement_day": "2026-03-05",
            "requester_id": "U123",
        }

    def test_음수_금액_문자열을_파싱한다(self, _base_fields: dict):
        data = SettlementData(**_base_fields, settlement_cost="-1,000,000원")
        assert data.settlement_cost == -1000000

    def test_음수_숫자_문자열을_파싱한다(self, _base_fields: dict):
        data = SettlementData(**_base_fields, settlement_cost="-50000")
        assert data.settlement_cost == -50000

    def test_이중_마이너스는_첫_부호만_인식한다(self, _base_fields: dict):
        data = SettlementData(**_base_fields, settlement_cost="--1000")
        assert data.settlement_cost == -1000

    def test_음수_int는_그대로_통과한다(self, _base_fields: dict):
        data = SettlementData(**_base_fields, settlement_cost=-1000)
        assert data.settlement_cost == -1000

    def test_양수_금액은_기존처럼_동작한다(self, _base_fields: dict):
        data = SettlementData(**_base_fields, settlement_cost="1,000,000원")
        assert data.settlement_cost == 1000000

    def test_None은_그대로_통과한다(self, _base_fields: dict):
        data = SettlementData(**_base_fields, settlement_cost=None)
        assert data.settlement_cost is None

    def test_빈_문자열은_None을_반환한다(self, _base_fields: dict):
        data = SettlementData(**_base_fields, settlement_cost="")
        assert data.settlement_cost is None
