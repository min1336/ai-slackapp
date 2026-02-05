from __future__ import annotations

from app.models import SettlementRow


class TestSettlementRow:
    """SettlementRow 단위 테스트"""

    def test_to_row_컬럼_순서를_확인한다(self):
        """to_row()가 올바른 순서로 데이터를 반환하는지 확인"""
        row = SettlementRow(
            settlement_day="2025-01-28",
            user_name="작성자",
            customer_name="고객",
            booking_key="BK-001",
            company_name="업체1",
            company_sub_name="업체2",
            settlement_cost="100000",
            carmore_cost="5000",
            user_refund_cost="10000",
            description="내용",
            status="승인",
            approver_name="승인자",
            issue_type="이슈",
            sales_channel="채널",
            note="비고",
        )

        result = row.to_row()

        # 예상 컬럼 순서 확인 (note는 맨 마지막에 추가하여 기존 시트 호환성 유지)
        assert result[0] == "2025-01-28"  # 정산기준일
        assert result[1] == "작성자"  # 작성자
        assert result[2] == "이슈"  # 이슈사항
        assert result[3] == "고객"  # 고객명
        assert result[4] == "BK-001"  # 예약번호
        assert result[5] == "업체1"  # 업체명1
        assert result[6] == "업체2"  # 업체명2(대신배차)
        assert result[7] == "100000"  # 정산기준금액
        assert result[8] == "5000"  # 카모아 부담비용
        assert result[9] == "10000"  # 고객환불금액
        assert result[10] == "채널"  # 판매채널
        assert result[11] == "내용"  # 내용
        assert result[12] == "승인"  # 처리
        assert result[13] == "승인자"  # 승인자
        # ... created_at, updated_at, thread_url 중간에 있음
        assert result[17] == "비고"  # 비고 (맨 마지막)

    def test_created_at_자동_생성을_확인한다(self):
        """created_at, updated_at이 자동 생성되는지 확인"""
        row = SettlementRow(
            settlement_day="2025-01-28",
            user_name="작성자",
            customer_name="고객",
            booking_key="BK-001",
            company_name="업체",
            company_sub_name="",
            settlement_cost="100000",
            carmore_cost="",
            user_refund_cost="",
            description="",
            status="승인",
            approver_name="승인자",
        )

        assert row.created_at != ""
        assert row.updated_at != ""
        print(f"created_at: {row.created_at}")
        print(f"updated_at: {row.updated_at}")

    def test_to_row_길이를_확인한다(self):
        """to_row()가 18개 컬럼을 반환하는지 확인 (note 필드 추가됨)"""
        row = SettlementRow(
            settlement_day="2025-01-28",
            user_name="작성자",
            customer_name="고객",
            booking_key="BK-001",
            company_name="업체",
            company_sub_name="",
            settlement_cost="100000",
            carmore_cost="",
            user_refund_cost="",
            description="",
            status="승인",
            approver_name="승인자",
        )

        result = row.to_row()
        assert len(result) == 18  # note 필드 추가로 17 → 18
