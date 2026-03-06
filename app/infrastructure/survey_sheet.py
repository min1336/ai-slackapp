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
