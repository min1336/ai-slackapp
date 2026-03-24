from __future__ import annotations

from datetime import date, datetime, timedelta

from app.core import get_logger
from app.models.analysis import (
    AnalysisResult,
    CrossVerificationResult,
    FieldComparison,
)
from app.models.cancellation import ReservationData, SurveySubmission

logger = get_logger(__name__)

_DATE_FORMATS = ["%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y년 %m월 %d일"]


def _parse_date(date_str: str) -> date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


class CrossVerifier:
    """고객명 유무 + 날짜 비교 기반 교차검증."""

    def verify(
        self,
        analysis: AnalysisResult,
        reservation: ReservationData,
        submission: SurveySubmission,
    ) -> CrossVerificationResult:
        comparisons = self._compare_fields(analysis, reservation)
        verdict, reason = self._decide(comparisons)
        return CrossVerificationResult(
            verdict=verdict,
            reason=reason,
            field_comparisons=comparisons,
        )

    def _compare_fields(
        self,
        analysis: AnalysisResult,
        reservation: ReservationData,
    ) -> list[FieldComparison]:
        fields = analysis.extracted_fields
        comparisons: list[FieldComparison] = []

        # 고객명 유무
        doc_name = fields.get("고객명") or ""
        if doc_name:
            comparisons.append(FieldComparison("고객명", doc_name, "", "확인"))
        else:
            comparisons.append(FieldComparison("고객명", "", "", "확인불가"))

        # 날짜 비교
        doc_date_str = fields.get("날짜") or ""
        period_start = reservation.rental_period_start
        period_end = reservation.rental_period_end
        if not doc_date_str or period_start is None or period_end is None:
            comparisons.append(FieldComparison("날짜", doc_date_str, "", "확인불가"))
        else:
            parsed = _parse_date(doc_date_str)
            if parsed is None:
                comparisons.append(
                    FieldComparison("날짜", doc_date_str, "", "확인불가")
                )
            else:
                start = period_start.date() - timedelta(days=1)
                end = period_end.date() + timedelta(days=1)
                period_str = f"{period_start.date()}~{period_end.date()}"
                if start <= parsed <= end:
                    comparisons.append(
                        FieldComparison("날짜", doc_date_str, period_str, "일치")
                    )
                else:
                    comparisons.append(
                        FieldComparison("날짜", doc_date_str, period_str, "불일치")
                    )

        return comparisons

    @staticmethod
    def _decide(
        comparisons: list[FieldComparison],
    ) -> tuple[str, str]:
        """판정: 불일치 → 반려, 확인불가 → 보류, 나머지 → 승인."""
        mismatched = [c.field_name for c in comparisons if c.status == "불일치"]
        if mismatched:
            return "반려", f"불일치 필드: {', '.join(mismatched)}"

        unverifiable = [c.field_name for c in comparisons if c.status == "확인불가"]
        if unverifiable:
            return "보류", f"확인불가 필드: {', '.join(unverifiable)}"

        return "승인", "모든 필드 검증 통과"
