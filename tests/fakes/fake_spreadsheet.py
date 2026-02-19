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
        self.settlement_rows: dict[str, dict[str, str]] = {}
        self.issue_logs: dict[str, dict[str, str]] = {}
        self.completed_keys: set[str] = set()
        self.should_fail: bool = False

    def save_settlement_row(
        self,
        row: SettlementRow,
        sheet_name: str | None = None,
        *,
        is_update: bool = False,
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
        self.settlement_rows[row.booking_key] = row.to_dict()

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
        data = row.to_dict()
        data["sync_key"] = sync_key
        self.issue_logs[sync_key] = data

    def find_row_by_booking_key(
        self, booking_key: str, sheet_name: str | None = None
    ) -> int | None:
        """booking_key로 활성 행 번호 찾기 (정산완료 행은 제외)"""
        if booking_key in self.completed_keys:
            return None
        return 1 if booking_key in self.settlement_rows else None

    def is_settlement_completed(self, booking_key: str) -> bool:
        return booking_key in self.completed_keys

    def get_completed_booking_keys(self) -> set[str]:
        if self.should_fail:
            raise SpreadsheetError(
                message="Fake spreadsheet failure",
                details={"operation": "get_completed_booking_keys"},
            )
        return set(self.completed_keys)

    def update_settlement_note(self, booking_key: str, note: str) -> None:
        """비고 컬럼만 업데이트 (정산완료 행은 무시)"""
        if booking_key in self.completed_keys:
            return
        if booking_key in self.settlement_rows:
            self.settlement_rows[booking_key]["note"] = note

    def clear(self):
        """테스트 간 상태 초기화"""
        self.settlement_rows.clear()
        self.issue_logs.clear()
        self.completed_keys.clear()
        self.should_fail = False
