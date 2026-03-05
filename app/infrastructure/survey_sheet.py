from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Lock

import gspread

from app.core import get_logger
from app.models import SurveySubmission

logger = get_logger(__name__)

_FORMATTED_HEADERS = [
    "작성일자",
    "작성자",
    "예약번호",
    "연락처",
    "고객명",
    "업체명",
    "결항확인서 확인여부",
    "환불 진행여부",
    "업체 전달여부",
]

_PROCESSED_COL = "처리완료"


def _get_row_value(row: dict, keyword: str) -> str:
    """헤더에 keyword가 포함된 컬럼의 값을 반환한다 (공백 차이 무시)."""
    for key, value in row.items():
        if keyword in str(key):
            return str(value)
    return ""


class SurveySheetReader:
    """Jotform 설문 스프레드시트에서 응답을 읽고, 처리 상태를 기록한다."""

    def __init__(
        self,
        client_factory: Callable[[], gspread.Spreadsheet],
        sheet_name: str,
        formatted_sheet_name: str = "운영현황",
        *,
        client_refresh_minutes: int = 55,
    ) -> None:
        self._client_factory = client_factory
        self._sheet_name = sheet_name
        self._formatted_sheet_name = formatted_sheet_name

        self._client: gspread.Spreadsheet | None = None
        self._client_lock = Lock()
        self._client_created_at: datetime | None = None
        self._client_refresh_minutes = client_refresh_minutes

    def _get_client(self) -> gspread.Spreadsheet:
        with self._client_lock:
            now = datetime.now()
            should_refresh = (
                self._client is None
                or self._client_created_at is None
                or (now - self._client_created_at)
                > timedelta(minutes=self._client_refresh_minutes)
            )
            if should_refresh:
                self._client = self._client_factory()
                self._client_created_at = now
                logger.debug("survey_sheet_client_refreshed")
            return self._client  # type: ignore[return-value]

    def get_all_submissions(self) -> list[SurveySubmission]:
        """시트의 미처리 설문 응답을 반환한다 (처리완료 == TRUE 제외)."""
        worksheet = self._get_client().worksheet(self._sheet_name)
        rows = worksheet.get_all_records()
        submissions: list[SurveySubmission] = []

        for row in rows:
            if str(row.get(_PROCESSED_COL, "")).strip().upper() == "TRUE":
                continue

            submission_id = str(row.get("Submission ID", "")).strip()
            customer_name = str(row.get("1. 운전자 성함을 입력해주세요.", "")).strip()
            booking_key = str(
                row.get("2. 취소 및 환불 접수하실 예약번호를 입력해주세요.", "")
            ).strip()

            if not (submission_id and customer_name and booking_key):
                continue

            submission_date = str(row.get("Submission Date", "")).strip()
            company_name = str(_get_row_value(row, "업체명")).strip()
            phone = str(_get_row_value(row, "전화번호")).strip()
            image_url = str(_get_row_value(row, "결항확인서")).strip()
            note = str(_get_row_value(row, "추가적으로 상담")).strip()

            submissions.append(
                SurveySubmission(
                    submission_id=submission_id,
                    customer_name=customer_name,
                    booking_key=booking_key,
                    submission_date=submission_date,
                    company_name=company_name,
                    phone=phone,
                    image_url=image_url,
                    note=note,
                )
            )

        logger.info(
            "survey_submissions_loaded",
            count=len(submissions),
        )
        return submissions

    def mark_processed(self, submission_id: str) -> None:
        """원본 시트에서 해당 submission_id 행의 처리완료 컬럼에 TRUE를 기록한다."""
        worksheet = self._get_client().worksheet(self._sheet_name)
        headers = worksheet.row_values(1)

        # 처리완료 컬럼 찾기 (없으면 추가)
        if _PROCESSED_COL in headers:
            col_idx = headers.index(_PROCESSED_COL) + 1
        else:
            col_idx = len(headers) + 1
            worksheet.update_cell(1, col_idx, _PROCESSED_COL)

        # submission_id로 행 찾기
        try:
            cell = worksheet.find(submission_id)
        except Exception as e:
            if e.__class__.__name__ == "CellNotFound":
                logger.warning(
                    "survey_mark_processed_not_found",
                    submission_id=submission_id,
                )
                return
            raise

        if cell is None:
            return

        worksheet.update_cell(cell.row, col_idx, "TRUE")
        logger.info(
            "survey_marked_processed",
            submission_id=submission_id,
            row=cell.row,
        )

    def write_formatted_row(self, submission: SurveySubmission) -> None:
        """운영현황 시트에 포맷된 행을 추가한다."""
        spreadsheet = self._get_client()

        # 탭 가져오기 (없으면 생성)
        try:
            worksheet = spreadsheet.worksheet(self._formatted_sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(
                title=self._formatted_sheet_name,
                rows=100,
                cols=len(_FORMATTED_HEADERS),
            )
            worksheet.append_row(_FORMATTED_HEADERS)
            logger.info(
                "survey_formatted_sheet_created",
                sheet_name=self._formatted_sheet_name,
            )

        # 중복 체크 (예약번호 + 고객명으로)
        existing = worksheet.get_all_records()
        for row in existing:
            if (
                str(row.get("예약번호", "")).strip() == submission.booking_key
                and str(row.get("고객명", "")).strip() == submission.customer_name
            ):
                logger.debug(
                    "survey_formatted_row_exists",
                    booking_key=submission.booking_key,
                )
                return

        date_part = submission.submission_date
        date_str = date_part.split(" ")[0] if date_part else ""

        row_data = [
            date_str,  # 작성일자
            "",  # 작성자 (운영자 수기)
            submission.booking_key,  # 예약번호
            submission.phone,  # 연락처
            submission.customer_name,  # 고객명
            submission.company_name,  # 업체명
            "",  # 결항확인서 확인여부 (운영자 수기)
            "",  # 환불 진행여부 (운영자 수기)
            "",  # 업체 전달여부 (운영자 수기)
        ]
        worksheet.append_row(row_data)
        logger.info(
            "survey_formatted_row_written",
            booking_key=submission.booking_key,
            customer_name=submission.customer_name,
        )
