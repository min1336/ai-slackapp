from __future__ import annotations

from app.services.spreadsheet import (
    SettlementRow,
    append_settlement_row,
    get_spreadsheet_client,
)


class TestSpreadsheet:
    """스프레드시트 통합 테스트

    해당 테스트는 실제 스프레드 시트에 등록되니 테스트시 사용에 주의가 필요합니다.

    """

    def test_스프레드시트_연결을_확인한다(self):
        spreadsheet = get_spreadsheet_client()
        assert spreadsheet is not None
        print(f"스프레드시트 제목: {spreadsheet.title}")

    def test_시트_목록을_조회한다(self):
        spreadsheet = get_spreadsheet_client()
        worksheets = spreadsheet.worksheets()
        print(f"시트 목록: {[ws.title for ws in worksheets]}")
        assert len(worksheets) > 0

    def test_정산_데이터를_추가한다(self):
        """SettlementRow를 스프레드시트에 추가"""
        row = SettlementRow(
            settlement_day="2025-01-28",
            user_name="테스트유저",
            customer_name="테스트고객",
            booking_key="TEST-001",
            company_name="테스트업체",
            company_sub_name="대신배차업체",
            settlement_cost="100000",
            carmore_cost="5000",
            user_refund_cost="10000",
            description="통합테스트 데이터입니다",
            status="승인",
            approver_name="테스트승인자",
        )

        result = append_settlement_row(row)
        assert result is True

    def test_빈_필드가_있는_데이터를_추가한다(self):
        """선택 필드가 비어있는 데이터 추가 테스트"""
        row = SettlementRow(
            settlement_day="2025-01-28",
            user_name="테스트유저2",
            customer_name="고객2",
            booking_key="TEST-002",
            company_name="업체2",
            company_sub_name="",  # 빈 값
            settlement_cost="50000",
            carmore_cost="",  # 빈 값
            user_refund_cost="",  # 빈 값
            description="",  # 빈 값
            status="반려",
            approver_name="반려자",
        )

        result = append_settlement_row(row)
        assert result is True
