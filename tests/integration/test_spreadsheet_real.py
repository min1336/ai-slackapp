from __future__ import annotations

import os
import time
import uuid
from collections.abc import Generator
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import gspread
import pytest
from google.oauth2.service_account import Credentials

from app.config import get_app_config, get_spreadsheet_settings
from app.exceptions import SpreadsheetError
from app.infrastructure import spreadsheet as spreadsheet_module
from app.models import SETTLEMENT_FIELDS, SettlementRow

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

pytestmark = pytest.mark.integration_real


def _is_quota_error(error: Exception) -> bool:
    return "Quota exceeded" in str(error) or "[429]" in str(error)


def _call_with_retry(fn, /, *args, **kwargs):
    delay_seconds = 1.0
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if not _is_quota_error(e):
                raise
            if attempt == 4:
                pytest.skip(
                    "Google Sheets API quota(429) 초과로 real 테스트를 스킵합니다."
                )
            time.sleep(delay_seconds)
            delay_seconds *= 2


def _run_sheet_fn_or_skip(fn, /, *args, **kwargs):
    try:
        return _call_with_retry(fn, *args, **kwargs)
    except SpreadsheetError as e:
        if _is_quota_error(e):
            pytest.skip("Google Sheets API quota(429) 초과로 real 테스트를 스킵합니다.")
        raise


def _sample_row(
    booking_key: str,
    *,
    status: str = "요청",
    user_name: str = "요청자",
    approver_name: str = "",
) -> SettlementRow:
    return SettlementRow(
        settlement_day="2025-01-28",
        user_name=user_name,
        customer_name="고객",
        booking_key=booking_key,
        company_name="업체",
        company_sub_name="서브업체",
        settlement_cost="100000",
        carmore_cost="1000",
        user_refund_cost="0",
        issue_type="결제 오류",
        sales_channel="직접판매",
        description="설명",
        status=status,
        approver_name=approver_name,
        thread_url="http://example.com/thread",
        note="비고",
        reviewer_name=approver_name,
    )


def _headers_for_settlement(extra_header: str | None = None) -> list[str]:
    field_to_header = get_app_config().spreadsheet.field_to_header("settlement")
    fields = [*SETTLEMENT_FIELDS, "settlement_completed"]
    base_headers = [field_to_header[field] for field in fields]

    booking_header = field_to_header["booking_key"]
    completed_header = field_to_header["settlement_completed"]
    leading_headers = [booking_header]
    if extra_header:
        leading_headers.append(extra_header)
    leading_headers.append(completed_header)

    trailing_headers = [h for h in base_headers if h not in set(leading_headers)]
    return leading_headers + trailing_headers


def _headers_for_issue_log(extra_header: str | None = None) -> list[str]:
    field_to_header = get_app_config().spreadsheet.field_to_header("issue_log")
    fields = [*SETTLEMENT_FIELDS, "sync_key"]
    base_headers = [field_to_header[field] for field in fields]

    sync_key_header = field_to_header["sync_key"]
    booking_header = field_to_header["booking_key"]
    leading_headers = [sync_key_header]
    if extra_header:
        leading_headers.append(extra_header)
    leading_headers.append(booking_header)

    trailing_headers = [h for h in base_headers if h not in set(leading_headers)]
    return leading_headers + trailing_headers


def _row_values_from_fields(
    *,
    sheet_type: str,
    headers: list[str],
    field_values: dict[str, str],
    extra_values: dict[str, str] | None = None,
) -> list[str]:
    field_to_header = get_app_config().spreadsheet.field_to_header(sheet_type)
    by_header = {
        field_to_header[field_name]: value
        for field_name, value in field_values.items()
        if field_name in field_to_header
    }
    if extra_values:
        by_header.update(extra_values)
    return [by_header.get(header, "") for header in headers]


def _value_at_header(worksheet, row_number: int, header: str) -> str:
    headers = _call_with_retry(worksheet.row_values, 1)
    header_index = headers.index(header) + 1
    return _call_with_retry(worksheet.cell, row_number, header_index).value or ""


@pytest.fixture(scope="session")
def real_spreadsheet():
    if os.getenv("RUN_REAL_INTEGRATION") != "1":
        pytest.skip("RUN_REAL_INTEGRATION=1 일 때만 real integration을 실행합니다.")

    app_config_file = os.getenv("APP_CONFIG_FILE")
    if not app_config_file:
        pytest.skip("APP_CONFIG_FILE=config.test.yaml 설정이 필요합니다.")

    project_root = Path(__file__).resolve().parents[2]
    default_config_path = (project_root / "config.yaml").resolve()
    selected_config_path = Path(app_config_file).expanduser()
    if not selected_config_path.is_absolute():
        selected_config_path = project_root / selected_config_path
    selected_config_path = selected_config_path.resolve()

    if selected_config_path == default_config_path:
        pytest.skip("운영/기본 config.yaml 대신 테스트 설정 파일을 사용하세요.")

    if get_app_config().spreadsheet.id.startswith("REPLACE_WITH_TEST_"):
        pytest.skip("config.test.yaml의 spreadsheet.id를 테스트 시트 ID로 교체하세요.")

    creds_file = get_spreadsheet_settings().credentials_file
    if not os.path.exists(creds_file):
        pytest.skip(f"credentials 파일이 없습니다: {creds_file}")

    credentials = Credentials.from_service_account_file(
        get_spreadsheet_settings().credentials_file,
        scopes=SCOPES,
    )
    client = gspread.authorize(credentials)
    return _call_with_retry(client.open_by_key, get_app_config().spreadsheet.id)


def _create_temp_worksheet(real_spreadsheet, prefix: str):
    title = f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    return _call_with_retry(
        real_spreadsheet.add_worksheet,
        title=title,
        rows=200,
        cols=40,
    )


@pytest.fixture
def settlement_worksheet(real_spreadsheet) -> Generator:
    worksheet = _create_temp_worksheet(real_spreadsheet, "it_settlement")
    try:
        yield worksheet
    finally:
        with suppress(pytest.skip.Exception):
            _call_with_retry(real_spreadsheet.del_worksheet, worksheet)


@pytest.fixture
def issue_log_worksheet(real_spreadsheet) -> Generator:
    worksheet = _create_temp_worksheet(real_spreadsheet, "it_issue_log")
    try:
        yield worksheet
    finally:
        with suppress(pytest.skip.Exception):
            _call_with_retry(real_spreadsheet.del_worksheet, worksheet)


def test_real_save_settlement_row_preserves_unmapped_column(
    monkeypatch,
    real_spreadsheet,
    settlement_worksheet,
) -> None:
    extra_header = "운영메모"
    headers = _headers_for_settlement(extra_header=extra_header)
    _call_with_retry(settlement_worksheet.append_row, headers)

    old_row = _sample_row("REAL-BK-001", status="요청", user_name="기존작성자")
    old_row.created_at = "2025-01-01 09:00:00"
    old_row.updated_at = "2025-01-01 09:00:00"
    old_data = old_row.to_dict()
    old_data["settlement_completed"] = "FALSE"
    _call_with_retry(
        settlement_worksheet.append_row,
        _row_values_from_fields(
            sheet_type="settlement",
            headers=headers,
            field_values=old_data,
            extra_values={extra_header: "KEEP"},
        ),
    )

    monkeypatch.setattr(
        spreadsheet_module,
        "get_spreadsheet_client",
        lambda: real_spreadsheet,
    )

    new_row = _sample_row(
        "REAL-BK-001",
        status="승인",
        user_name="새작성자",
        approver_name="검토자",
    )
    _run_sheet_fn_or_skip(
        spreadsheet_module.save_settlement_row,
        new_row,
        sheet_name=settlement_worksheet.title,
    )

    field_to_header = get_app_config().spreadsheet.field_to_header("settlement")
    values = _call_with_retry(settlement_worksheet.get_all_values)
    assert len(values) == 2
    assert _value_at_header(settlement_worksheet, 2, extra_header) == "KEEP"
    assert (
        _value_at_header(settlement_worksheet, 2, field_to_header["created_at"])
        == "2025-01-01 09:00:00"
    )
    assert (
        _value_at_header(settlement_worksheet, 2, field_to_header["status"]) == "승인"
    )


def test_real_save_settlement_row_fails_when_required_header_missing(
    monkeypatch,
    real_spreadsheet,
    settlement_worksheet,
) -> None:
    headers = _headers_for_settlement()
    headers.remove(
        get_app_config().spreadsheet.field_to_header("settlement")[
            "settlement_completed"
        ]
    )
    _call_with_retry(settlement_worksheet.append_row, headers)

    monkeypatch.setattr(
        spreadsheet_module,
        "get_spreadsheet_client",
        lambda: real_spreadsheet,
    )

    row = _sample_row("REAL-BK-002")
    with pytest.raises(SpreadsheetError, match="settlement_completed"):
        _run_sheet_fn_or_skip(
            spreadsheet_module.save_settlement_row,
            row,
            sheet_name=settlement_worksheet.title,
        )


def test_real_append_issue_log_row_upserts_by_sync_key(
    monkeypatch,
    real_spreadsheet,
    issue_log_worksheet,
) -> None:
    extra_header = "운영메모"
    headers = _headers_for_issue_log(extra_header=extra_header)
    _call_with_retry(issue_log_worksheet.append_row, headers)

    old_row = _sample_row("REAL-LOG-001", status="요청")
    old_data = old_row.to_dict()
    old_data["sync_key"] = "777"
    _call_with_retry(
        issue_log_worksheet.append_row,
        _row_values_from_fields(
            sheet_type="issue_log",
            headers=headers,
            field_values=old_data,
            extra_values={extra_header: "LEGACY"},
        ),
    )

    monkeypatch.setattr(
        spreadsheet_module,
        "get_spreadsheet_client",
        lambda: real_spreadsheet,
    )
    monkeypatch.setattr(
        get_app_config().spreadsheet.sheets.issue_log,
        "name",
        issue_log_worksheet.title,
    )

    new_row = _sample_row("REAL-LOG-001", status="반려", approver_name="반려자")
    _run_sheet_fn_or_skip(
        spreadsheet_module.append_issue_log_row,
        new_row,
        sync_key="777",
    )

    values = _call_with_retry(issue_log_worksheet.get_all_values)
    field_to_header = get_app_config().spreadsheet.field_to_header("issue_log")
    assert len(values) == 2
    assert _value_at_header(issue_log_worksheet, 2, extra_header) == "LEGACY"
    assert _value_at_header(issue_log_worksheet, 2, field_to_header["status"]) == "반려"
