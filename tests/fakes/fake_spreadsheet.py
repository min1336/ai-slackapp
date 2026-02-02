"""인메모리 스프레드시트 Fake"""

from __future__ import annotations

from app.models.settlement import SettlementRow


class FakeSpreadsheet:
    """Google Sheets 대신 사용할 인메모리 Fake

    실제 spreadsheet 모듈의 함수들과 동일한 시그니처를 가진 메서드를 제공합니다.
    테스트에서 monkeypatch로 실제 함수를 이 Fake의 메서드로 교체하여 사용합니다.
    """

    def __init__(self):
        self.settlement_rows: dict[str, list[str]] = {}
        self.approval_logs: list[list[str]] = []
        self.should_fail: bool = False

    def save_settlement_row(
        self, row: SettlementRow, sheet_name: str | None = None
    ) -> bool:
        """settlement 시트에 저장 (동일 키면 업데이트)"""
        if self.should_fail:
            return False
        self.settlement_rows[row.booking_key] = row.to_row()
        return True

    def append_approval_log_row(self, row: SettlementRow) -> bool:
        """승인 로그는 항상 추가"""
        if self.should_fail:
            return False
        self.approval_logs.append(row.to_row())
        return True

    def find_row_by_booking_key(
        self, booking_key: str, sheet_name: str | None = None
    ) -> int | None:
        """booking_key로 행 번호 찾기"""
        return 1 if booking_key in self.settlement_rows else None

    def clear(self):
        """테스트 간 상태 초기화"""
        self.settlement_rows.clear()
        self.approval_logs.clear()
        self.should_fail = False
