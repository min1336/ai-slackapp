from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.core import get_logger
from app.infrastructure.protocols import ImageAnalysisGateway
from app.models.analysis import (
    AnalysisResult,
    CrossVerificationResult,
    FieldComparison,
)
from app.models.cancellation import ReservationData, SurveySubmission

logger = get_logger(__name__)

_DATE_FORMATS = ["%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y년 %m월 %d일"]
_AIRLINE_DOC_TYPES = {"항공사 운항정보확인서"}
_VALID_DOC_TYPES = {"항공사 운항정보확인서", "해운사 결항확인서"}


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name)


def _digits_only(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def _parse_date(date_str: str) -> date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


class CrossVerifier:
    """규칙 기반 + AI 하이브리드 교차검증."""

    def __init__(self, gateway: ImageAnalysisGateway | None = None) -> None:
        self._gateway = gateway

    def verify(
        self,
        analysis: AnalysisResult,
        reservation: ReservationData,
        submission: SurveySubmission,
    ) -> CrossVerificationResult:
        comparisons = self._compare_fields(analysis, reservation, submission)
        verdict = self._rule_based_verdict(analysis, comparisons)

        if verdict is not None:
            reason = self._build_reason(verdict, comparisons)
            return CrossVerificationResult(
                verdict=verdict,
                reason=reason,
                field_comparisons=comparisons,
            )

        if self._gateway is not None:
            return self._ai_verdict(analysis, reservation, comparisons)

        return CrossVerificationResult(
            verdict="보류",
            reason="자동 판단 불가 — 수동 검토 필요",
            field_comparisons=comparisons,
            ai_used=False,
        )

    def _compare_fields(
        self,
        analysis: AnalysisResult,
        reservation: ReservationData,
        submission: SurveySubmission,
    ) -> list[FieldComparison]:
        fields = analysis.extracted_fields
        is_airline = analysis.document_type in _AIRLINE_DOC_TYPES
        comparisons: list[FieldComparison] = []

        # 고객명
        doc_name = fields.get("고객명") or ""
        res_name = reservation.customer_name
        if is_airline and not doc_name:
            comparisons.append(
                FieldComparison("고객명", doc_name, res_name, "비교불필요")
            )
        elif not doc_name:
            comparisons.append(
                FieldComparison("고객명", doc_name, res_name, "확인불가")
            )
        else:
            a = _normalize_name(doc_name)
            b = _normalize_name(res_name)
            status = "일치" if (a in b or b in a) else "불일치"
            comparisons.append(FieldComparison("고객명", doc_name, res_name, status))

        # 예약번호 — 항공 PNR ≠ 렌트카 예약번호이므로 비교 불필요
        doc_key = fields.get("예약번호") or ""
        res_key = reservation.booking_key
        comparisons.append(FieldComparison("예약번호", doc_key, res_key, "비교불필요"))

        # 날짜
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
                status = "일치" if start <= parsed <= end else "불일치"
                period_str = f"{period_start.date()}~{period_end.date()}"
                comparisons.append(
                    FieldComparison("날짜", doc_date_str, period_str, status)
                )

        # 연락처 (submission.phone vs reservation.phone)
        sub_phone = _digits_only(submission.phone)
        res_phone = _digits_only(reservation.phone)
        if not sub_phone or not res_phone:
            comparisons.append(
                FieldComparison(
                    "연락처", submission.phone, reservation.phone, "확인불가"
                )
            )
        else:
            status = "일치" if sub_phone == res_phone else "불일치"
            comparisons.append(
                FieldComparison("연락처", submission.phone, reservation.phone, status)
            )

        return comparisons

    def _rule_based_verdict(
        self,
        analysis: AnalysisResult,
        comparisons: list[FieldComparison],
    ) -> str | None:
        # 문서 유형 확인
        if analysis.document_type not in _VALID_DOC_TYPES:
            return None

        # 이미지 품질 문제
        if analysis.quality_issues:
            return None

        # 결항사유 확인
        if not (analysis.extracted_fields.get("결항사유") or ""):
            return None

        # 편명 필수 — 항공편 또는 선편이 추출되어야 자동 판단 가능
        flight = (
            analysis.extracted_fields.get("항공편")
            or analysis.extracted_fields.get("선편")
            or ""
        )
        if not flight:
            return None

        # 불일치 체크
        mismatched = [c for c in comparisons if c.status == "불일치"]
        if mismatched:
            return "반려"

        # 고객명 확인불가이면 근거 부족
        name_cmp = [c for c in comparisons if c.field_name == "고객명"]
        if name_cmp and all(c.status == "확인불가" for c in name_cmp):
            return None

        return "승인"

    def _ai_verdict(
        self,
        analysis: AnalysisResult,
        reservation: ReservationData,
        comparisons: list[FieldComparison],
    ) -> CrossVerificationResult:
        comparison_text = "\n".join(
            f"- {c.field_name}: 문서={c.document_value!r},"
            f" 예약={c.reservation_value!r}, 상태={c.status}"
            for c in comparisons
        )
        json_instruction = '{"verdict": "승인|반려|보류", "reasoning": "판단 이유"}'
        prompt = (
            "다음은 결항확인서 교차검증 결과입니다. 판단이 필요합니다.\n\n"
            f"문서 유형: {analysis.document_type}\n"
            f"요약: {analysis.summary}\n"
            f"추출 필드: {analysis.extracted_fields}\n"
            f"품질 이슈: {analysis.quality_issues}\n\n"
            f"필드 비교:\n{comparison_text}\n\n"
            f"예약자명: {reservation.customer_name}\n"
            f"예약번호: {reservation.booking_key}\n\n"
            f"다음 JSON 형식으로만 응답하세요: {json_instruction}"
        )

        try:
            response = self._gateway.analyze_images(images=[], prompt=prompt)
            verdict = response.get("verdict", "보류")
            reasoning = response.get("reasoning", "")
            if verdict not in ("승인", "반려", "보류"):
                verdict = "보류"
            return CrossVerificationResult(
                verdict=verdict,
                reason=f"AI 판단: {reasoning}",
                field_comparisons=comparisons,
                ai_used=True,
                ai_reasoning=reasoning,
            )
        except Exception:
            logger.exception("ai_verdict_failed")
            return CrossVerificationResult(
                verdict="보류",
                reason="AI 판단 실패 — 수동 검토 필요",
                field_comparisons=comparisons,
                ai_used=True,
            )

    def _build_reason(self, verdict: str, comparisons: list[FieldComparison]) -> str:
        if verdict == "반려":
            mismatched = [c.field_name for c in comparisons if c.status == "불일치"]
            return f"불일치 필드: {', '.join(mismatched)}"
        if verdict == "승인":
            return "모든 필드 검증 통과"
        return "자동 판단 불가 — 수동 검토 필요"
