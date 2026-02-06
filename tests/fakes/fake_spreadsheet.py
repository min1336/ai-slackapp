"""인메모리 스프레드시트 Fake"""

from __future__ import annotations

from app.exceptions import SpreadsheetError
from app.models.settlement import SettlementRow


class FakeSpreadsheet:
    """Google Sheets 대신 사용할 인메모리 Fake (SpreadsheetGateway 호환).

    Protocol 기반 의존성 주입으로 서비스 함수에 직접 전달하거나,
    monkeypatch로 모듈-레벨 함수를 교체하여 사용합니다.
    """

    def __init__(self):
        self.settlement_rows: dict[str, list[str]] = {}
        self.issue_logs: dict[str, list[str]] = {}
        self.should_fail: bool = False

    def save_settlement_row(
        self, row: SettlementRow, sheet_name: str | None = None
    ) -> None:
        """settlement 시트에 저장 (동일 키면 업데이트)

        Raises:
            SpreadsheetError: If should_fail is True
        """
        if self.should_fail:
            raise SpreadsheetError(
                message="Fake spreadsheet failure",
                details={"booking_key": row.booking_key},
            )
        self.settlement_rows[row.booking_key] = row.to_row()

    def append_issue_log_row(self, row: SettlementRow, sync_key: str) -> None:
        """이슈 로그는 sync_key 기준으로 upsert

        Raises:
            SpreadsheetError: If should_fail is True
        """
        if self.should_fail:
            raise SpreadsheetError(
                message="Fake spreadsheet failure",
                details={"booking_key": row.booking_key},
            )
        self.issue_logs[sync_key] = row.to_row() + [sync_key]

    def find_row_by_booking_key(
        self, booking_key: str, sheet_name: str | None = None
    ) -> int | None:
        """booking_key로 행 번호 찾기"""
        return 1 if booking_key in self.settlement_rows else None

    def clear(self):
        """테스트 간 상태 초기화"""
        self.settlement_rows.clear()
        self.issue_logs.clear()
        self.should_fail = False
