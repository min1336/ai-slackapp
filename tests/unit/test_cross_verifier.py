from __future__ import annotations

from datetime import datetime

from app.models.analysis import AnalysisResult
from app.models.cancellation import ReservationData
from app.services.cancellation_image_service import CancellationImageService
from app.services.reservation_locator import ReservationLocation


def _analysis(date_str: str = "2026-02-27") -> AnalysisResult:
    fields: dict = {"고객명": "박성구"}
    if date_str is not None:
        fields["날짜"] = date_str
    return AnalysisResult(extracted_fields=fields)


def _location(
    start: datetime | None = datetime(2026, 2, 27, 21, 0),
    end: datetime | None = datetime(2026, 3, 2, 19, 30),
) -> ReservationLocation:
    return ReservationLocation(
        data=ReservationData(
            rental_period_start=start,
            rental_period_end=end,
        ),
        channel="C_RES",
        thread_ts="1234.5678",
    )


class TestCheckDateRange:
    """CancellationImageService._check_date_range 단위 테스트."""

    def test_날짜_기간내_승인(self):
        result = CancellationImageService._check_date_range(_analysis(), _location())
        assert result.verdict == "승인"

    def test_날짜_하루전도_허용(self):
        """start - 1일까지 허용."""
        result = CancellationImageService._check_date_range(
            _analysis("2026-02-26"), _location()
        )
        assert result.verdict == "승인"

    def test_날짜_하루후도_허용(self):
        """end + 1일까지 허용."""
        result = CancellationImageService._check_date_range(
            _analysis("2026-03-03"), _location()
        )
        assert result.verdict == "승인"

    def test_날짜_기간밖_반려(self):
        result = CancellationImageService._check_date_range(
            _analysis("2026-03-15"), _location()
        )
        assert result.verdict == "반려"
        assert "대여기간" in result.reason

    def test_날짜_빈값_보류(self):
        result = CancellationImageService._check_date_range(_analysis(""), _location())
        assert result.verdict == "보류"

    def test_날짜_키없음_보류(self):
        analysis = AnalysisResult(extracted_fields={"고객명": "박성구"})
        result = CancellationImageService._check_date_range(analysis, _location())
        assert result.verdict == "보류"

    def test_날짜_파싱실패_보류(self):
        result = CancellationImageService._check_date_range(
            _analysis("invalid-date"), _location()
        )
        assert result.verdict == "보류"

    def test_대여기간_없으면_보류(self):
        result = CancellationImageService._check_date_range(
            _analysis(), _location(start=None, end=None)
        )
        assert result.verdict == "보류"

    def test_다양한_날짜포맷_지원(self):
        """YYYY.MM.DD, YYYY/MM/DD 등도 파싱 가능."""
        for fmt in ["2026.02.27", "2026/02/27"]:
            result = CancellationImageService._check_date_range(
                _analysis(fmt), _location()
            )
            assert result.verdict == "승인", f"{fmt} 파싱 실패"
