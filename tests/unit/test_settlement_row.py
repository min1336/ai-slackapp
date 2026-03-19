from __future__ import annotations

from app.models import SETTLEMENT_FIELDS, SettlementRow
from app.models.settlement import SettlementStatus
from tests.factories import SettlementDataFactory


class TestSettlementRow:
    """SettlementRow 단위 테스트"""

    def test_to_dict_키를_확인한다(self):
        """to_dict()가 올바른 키를 반환하는지 확인"""
        row = SettlementRow(
            settlement_day="2025-01-28",
            user_name="작성자",
            customer_name="고객",
            booking_key="BK-001",
            company_name="업체1",
            company_sub_name="업체2",
            settlement_cost="100000",
            carmore_cost="5000",
            seller_channel_cost="",
            user_refund_cost="10000",
            description="내용",
            status="승인",
            approver_name="승인자",
            issue_type="이슈",
            sales_channel="채널",
            note="비고",
            reviewer_name="검토자",
            rejection_reason="사유",
        )

        result = row.to_dict()
        assert result["settlement_day"] == "2025-01-28"
        assert result["user_name"] == "작성자"
        assert result["issue_type"] == "이슈"
        assert result["customer_name"] == "고객"
        assert result["booking_key"] == "BK-001"
        assert result["company_name"] == "업체1"
        assert result["company_sub_name"] == "업체2"
        assert result["settlement_cost"] == "100000"
        assert result["carmore_cost"] == "5000"
        assert result["user_refund_cost"] == "10000"
        assert result["sales_channel"] == "채널"
        assert result["description"] == "내용"
        assert result["status"] == "승인"
        assert result["approver_name"] == "승인자"
        assert result["note"] == "비고"
        assert result["reviewer_name"] == "검토자"
        assert result["rejection_reason"] == "사유"

    def test_to_dict_settlement_completed_제외(self):
        """to_dict()에서 settlement_completed가 제외되는지 확인"""
        row = SettlementRow(
            settlement_day="2025-01-28",
            user_name="작성자",
            customer_name="고객",
            booking_key="BK-001",
            company_name="업체",
            company_sub_name="",
            settlement_cost="100000",
            carmore_cost="",
            seller_channel_cost="",
            user_refund_cost="",
            description="",
            status="승인",
            approver_name="승인자",
        )

        result = row.to_dict()
        assert "settlement_completed" not in result

    def test_from_settlement_data_타임스탬프_생성(self):
        """from_settlement_data()가 타임스탬프를 생성하는지 확인"""
        data = SettlementDataFactory.create()
        row = SettlementRow.from_settlement_data(
            data=data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
        )
        assert row.created_at != ""
        assert row.updated_at != ""

    def test_to_dict_필드_수_확인(self):
        """to_dict()가 21개 필드를 반환하는지 확인"""
        row = SettlementRow(
            settlement_day="2025-01-28",
            user_name="작성자",
            customer_name="고객",
            booking_key="BK-001",
            company_name="업체",
            company_sub_name="",
            settlement_cost="100000",
            carmore_cost="",
            seller_channel_cost="",
            user_refund_cost="",
            description="",
            status="승인",
            approver_name="승인자",
        )

        result = row.to_dict()
        assert len(result) == 22

    def test_to_dict_키가_SETTLEMENT_FIELDS와_일치(self):
        """to_dict()의 키가 SETTLEMENT_FIELDS와 동일한지 확인"""
        row = SettlementRow(
            settlement_day="2025-01-28",
            user_name="작성자",
            customer_name="고객",
            booking_key="BK-001",
            company_name="업체",
            company_sub_name="",
            settlement_cost="100000",
            carmore_cost="",
            seller_channel_cost="",
            user_refund_cost="",
            description="",
            status="승인",
            approver_name="승인자",
        )

        result = row.to_dict()
        assert set(result.keys()) == set(SETTLEMENT_FIELDS)
