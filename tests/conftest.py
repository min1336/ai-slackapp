"""공유 pytest fixture 정의"""

from __future__ import annotations

import pytest

from app.config import DatabaseProperties
from app.models.settlement import SettlementData, SettlementRow, SettlementStatus
from tests.factories import SettlementDataFactory
from tests.fakes.fake_spreadsheet import FakeSpreadsheet


@pytest.fixture
def sample_settlement_data() -> SettlementData:
    """테스트용 SettlementData 샘플 (팩토리 기반)"""
    return SettlementDataFactory.create(
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
def sample_settlement_row(sample_settlement_data: SettlementData) -> SettlementRow:
    """테스트용 SettlementRow 샘플 (sample_settlement_data 기반)"""
    return SettlementRow.from_settlement_data(
        data=sample_settlement_data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="https://test.slack.com/thread",
    )


@pytest.fixture
def fake_spreadsheet() -> FakeSpreadsheet:
    """테스트용 FakeSpreadsheet 인스턴스"""
    return FakeSpreadsheet()


@pytest.fixture
def db_configured(monkeypatch):
    """get_database_settings()가 DB 설정 완료 상태를 반환하도록 mock."""
    fake = DatabaseProperties(host="test-host", password="test-pw")
    monkeypatch.setattr(
        "app.services.settlement_service.get_database_settings",
        lambda: fake,
    )
