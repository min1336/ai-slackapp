"""SpreadsheetService 단위 테스트 — Mock gspread 주입."""

from __future__ import annotations

from unittest.mock import MagicMock

import gspread
import pytest
from gspread import Worksheet
from gspread.exceptions import GSpreadException

from app.exceptions import SpreadsheetError
from app.infrastructure.column_mapper import ColumnMapping
from app.infrastructure.spreadsheet import SpreadsheetService, _merge_with_existing_row
from app.models import SettlementRow, SettlementStatus
from tests.factories import SettlementDataFactory

# ── 테스트용 field→header 매핑 (config.yaml과 동일 구조) ─────────────

_FIELD_TO_HEADER: dict[str, str] = {
    "settlement_day": "정산기준일",
    "user_name": "작성자",
    "customer_name": "고객명",
    "booking_key": "예약번호",
    "company_name": "업체명1",
    "company_sub_name": "업체명2(대신배차)",
    "settlement_cost": "정산기준금액",
    "carmore_cost": "카모아 부담비용",
    "user_refund_cost": "고객환불금액",
    "description": "내용",
    "status": "처리",
    "approver_name": "승인자",
    "issue_type": "이슈사항",
    "sales_channel": "판매채널",
    "created_at": "등록시간",
    "updated_at": "수정시간",
    "thread_url": "스레드 링크",
    "note": "비고",
    "reviewer_name": "반려자",
    "rejection_reason": "고객 정보 오류",
}

_SETTLEMENT_HEADERS: list[str] = [
    *_FIELD_TO_HEADER.values(),
    "정산완료",
]

_ISSUE_LOG_HEADERS: list[str] = [
    *_FIELD_TO_HEADER.values(),
    "sync_key",
]


def _field_to_header(sheet_type: str) -> dict[str, str]:
    base = dict(_FIELD_TO_HEADER)
    if sheet_type == "settlement":
        base["settlement_completed"] = "정산완료"
    elif sheet_type == "issue_log":
        base["sync_key"] = "sync_key"
    return base


def _sheet_name(sheet_type: str) -> str:
    return {"settlement": "정산", "issue_log": "정산이슈로그"}[sheet_type]


def _make_row() -> SettlementRow:
    data = SettlementDataFactory.create(
        booking_key="BK-001",
        customer_name="홍길동",
        company_name="테스트업체",
        settlement_cost=100000,
    )
    return SettlementRow.from_settlement_data(
        data=data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="https://test.slack.com/thread",
    )


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_worksheet():
    ws = MagicMock(spec=Worksheet)
    ws.title = "정산"
    ws.row_values.return_value = _SETTLEMENT_HEADERS
    ws.findall.return_value = []
    ws.append_row.return_value = None
    return ws


@pytest.fixture
def mock_spreadsheet(mock_worksheet):
    ss = MagicMock(spec=gspread.Spreadsheet)
    ss.worksheet.return_value = mock_worksheet
    return ss


@pytest.fixture
def service(mock_spreadsheet):
    return SpreadsheetService(
        client_factory=lambda: mock_spreadsheet,
        sheet_name_resolver=_sheet_name,
        field_to_header_resolver=_field_to_header,
    )


# ── save_settlement_row ──────────────────────────────────────────────


class TestSaveSettlementRow:
    def test_신규_행_append_row_호출(self, service, mock_worksheet):
        row = _make_row()

        service.save_settlement_row(row)

        mock_worksheet.append_row.assert_called_once()
        args = mock_worksheet.append_row.call_args[0][0]
        # booking_key가 row 데이터에 포함되어야 함
        assert "BK-001" in args

    def test_업데이트_행_update_cells_호출(self, service, mock_worksheet):
        row = _make_row()

        # findall이 booking_key 컬럼에 매치 반환
        cell = MagicMock()
        cell.col = _SETTLEMENT_HEADERS.index("예약번호") + 1  # 1-based
        cell.row = 5
        mock_worksheet.findall.return_value = [cell]

        # row_values(5) → 기존 행 반환 (row_values(1) = headers에 주의)
        existing_row = [""] * len(_SETTLEMENT_HEADERS)
        existing_row[_SETTLEMENT_HEADERS.index("예약번호")] = "BK-001"
        existing_row[_SETTLEMENT_HEADERS.index("정산완료")] = "FALSE"

        def _row_values(row_num):
            if row_num == 1:
                return _SETTLEMENT_HEADERS
            return existing_row

        mock_worksheet.row_values.side_effect = _row_values
        mock_worksheet.range.return_value = [
            MagicMock() for _ in range(len(existing_row))
        ]

        service.save_settlement_row(row, is_update=True)

        mock_worksheet.update_cells.assert_called_once()
        mock_worksheet.append_row.assert_not_called()

    def test_업데이트_행_미발견시_폴백_INSERT(self, service, mock_worksheet):
        row = _make_row()

        # findall returns empty → row not found
        mock_worksheet.findall.return_value = []

        service.save_settlement_row(row, is_update=True)

        mock_worksheet.append_row.assert_called_once()
        mock_worksheet.update_cells.assert_not_called()

    def test_GSpreadException을_SpreadsheetError로_래핑(self, service, mock_worksheet):
        row = _make_row()
        mock_worksheet.append_row.side_effect = GSpreadException("test error")

        with pytest.raises(SpreadsheetError) as exc_info:
            service.save_settlement_row(row)

        assert "Failed to save settlement row" in str(exc_info.value)
        assert exc_info.value.details["booking_key"] == "BK-001"

    def test_sheet_name_기본값은_settlement(self, service, mock_spreadsheet):
        row = _make_row()

        service.save_settlement_row(row)

        mock_spreadsheet.worksheet.assert_called_with("정산")


# ── append_issue_log_row ─────────────────────────────────────────────


class TestAppendIssueLogRow:
    @pytest.fixture(autouse=True)
    def _setup_issue_log_ws(self, mock_spreadsheet):
        """이슈로그 시트용 워크시트 모킹."""
        ws = MagicMock(spec=Worksheet)
        ws.title = "정산이슈로그"
        ws.row_values.return_value = _ISSUE_LOG_HEADERS
        ws.findall.return_value = []
        ws.append_row.return_value = None
        mock_spreadsheet.worksheet.return_value = ws
        self.ws = ws

    def test_신규_로그_append_row_호출(self, service):
        row = _make_row()

        service.append_issue_log_row(row, "sync-001")

        self.ws.append_row.assert_called_once()

    def test_중복_sync_key는_skip(self, service):
        row = _make_row()

        # findall이 sync_key 컬럼에 매치 반환
        sync_key_col = _ISSUE_LOG_HEADERS.index("sync_key") + 1
        cell = MagicMock()
        cell.col = sync_key_col
        self.ws.findall.return_value = [cell]

        service.append_issue_log_row(row, "sync-001")

        self.ws.append_row.assert_not_called()

    def test_GSpreadException을_SpreadsheetError로_래핑(self, service):
        row = _make_row()
        self.ws.append_row.side_effect = GSpreadException("test error")

        with pytest.raises(SpreadsheetError) as exc_info:
            service.append_issue_log_row(row, "sync-001")

        assert "Failed to append issue log" in str(exc_info.value)


# ── find_row_by_booking_key ──────────────────────────────────────────


class TestFindRowByBookingKey:
    def test_활성_행_번호_반환(self, service, mock_worksheet):
        booking_col = _SETTLEMENT_HEADERS.index("예약번호") + 1
        cell = MagicMock()
        cell.col = booking_col
        cell.row = 3
        mock_worksheet.findall.return_value = [cell]

        # row_values 호출 시 정산완료=FALSE인 행 반환
        def _row_values(row_num):
            if row_num == 1:
                return _SETTLEMENT_HEADERS
            row = [""] * len(_SETTLEMENT_HEADERS)
            row[_SETTLEMENT_HEADERS.index("예약번호")] = "BK-001"
            row[_SETTLEMENT_HEADERS.index("정산완료")] = "FALSE"
            return row

        mock_worksheet.row_values.side_effect = _row_values

        result = service.find_row_by_booking_key("BK-001", "정산")

        assert result == 3

    def test_정산완료_행은_None_반환(self, service, mock_worksheet):
        booking_col = _SETTLEMENT_HEADERS.index("예약번호") + 1
        cell = MagicMock()
        cell.col = booking_col
        cell.row = 3
        mock_worksheet.findall.return_value = [cell]

        def _row_values(row_num):
            if row_num == 1:
                return _SETTLEMENT_HEADERS
            row = [""] * len(_SETTLEMENT_HEADERS)
            row[_SETTLEMENT_HEADERS.index("예약번호")] = "BK-001"
            row[_SETTLEMENT_HEADERS.index("정산완료")] = "TRUE"
            return row

        mock_worksheet.row_values.side_effect = _row_values

        result = service.find_row_by_booking_key("BK-001", "정산")

        assert result is None

    def test_미존재시_None_반환(self, service, mock_worksheet):
        mock_worksheet.findall.return_value = []

        result = service.find_row_by_booking_key("NONEXIST", "정산")

        assert result is None


# ── _merge_with_existing_row ─────────────────────────────────────────


class TestMergeWithExistingRow:
    def test_매핑_안된_컬럼_보존(self):
        mapping = ColumnMapping(field_to_index={"a": 0, "b": 1})
        existing = ["old_a", "old_b", "unmapped_extra"]
        mapped = ["new_a", "new_b"]

        result = _merge_with_existing_row(existing, mapped, mapping)

        assert result[0] == "new_a"
        assert result[1] == "new_b"
        assert result[2] == "unmapped_extra"  # 보존됨

    def test_기존_행이_짧으면_확장(self):
        mapping = ColumnMapping(field_to_index={"a": 0, "b": 2})
        existing = ["old"]
        mapped = ["new_a", "", "new_b"]

        result = _merge_with_existing_row(existing, mapped, mapping)

        assert result[0] == "new_a"
        assert result[2] == "new_b"
        assert len(result) >= 3


# ── 클라이언트 TTL 갱신 ─────────────────────────────────────────────


class TestClientRefresh:
    def test_TTL_만료시_클라이언트_갱신(self):
        call_count = 0
        mock_ss = MagicMock(spec=gspread.Spreadsheet)

        def _factory():
            nonlocal call_count
            call_count += 1
            return mock_ss

        svc = SpreadsheetService(
            client_factory=_factory,
            sheet_name_resolver=_sheet_name,
            field_to_header_resolver=_field_to_header,
            client_refresh_minutes=0,  # 즉시 만료
        )

        svc._get_client()
        assert call_count == 1

        # 다시 호출 — refresh_minutes=0이므로 항상 갱신
        svc._get_client()
        assert call_count == 2

    def test_TTL_내에서는_갱신_안함(self):
        call_count = 0
        mock_ss = MagicMock(spec=gspread.Spreadsheet)

        def _factory():
            nonlocal call_count
            call_count += 1
            return mock_ss

        svc = SpreadsheetService(
            client_factory=_factory,
            sheet_name_resolver=_sheet_name,
            field_to_header_resolver=_field_to_header,
            client_refresh_minutes=60,  # 60분 (충분히 긴 TTL)
        )

        svc._get_client()
        svc._get_client()
        assert call_count == 1  # 한 번만 생성

    def test_갱신시_캐시_클리어(self):
        mock_ss = MagicMock(spec=gspread.Spreadsheet)

        svc = SpreadsheetService(
            client_factory=lambda: mock_ss,
            sheet_name_resolver=_sheet_name,
            field_to_header_resolver=_field_to_header,
            client_refresh_minutes=0,  # 즉시 만료
        )

        # 캐시에 값 추가
        svc._worksheet_cache.set("test", MagicMock())
        svc._mapping_cache.set("test", MagicMock())

        svc._get_client()

        # 갱신 후 캐시가 클리어되어야 함
        assert svc._worksheet_cache.get("test") is None
        assert svc._mapping_cache.get("test") is None
