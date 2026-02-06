"""공유 pytest fixture 정의"""

from __future__ import annotations

import pytest

from app.models.settlement import SettlementData
from tests.fakes.fake_spreadsheet import FakeSpreadsheet


@pytest.fixture
def sample_settlement_data() -> SettlementData:
    """테스트용 SettlementData 샘플"""
    return SettlementData(
        user_name="테스터",
        booking_key="TEST-001",
        company_name="테스트업체",
        customer_name="홍길동",
        settlement_day="2024-01-15",
        issue_type="결제 오류",
        settlement_cost=100000,
        requester_id="U12345678",
    )


@pytest.fixture
def fake_spreadsheet() -> FakeSpreadsheet:
    """테스트용 FakeSpreadsheet 인스턴스"""
    return FakeSpreadsheet()
