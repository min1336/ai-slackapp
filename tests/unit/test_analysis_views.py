from __future__ import annotations

import pytest

from app.models.analysis import AnalysisResult, CrossVerificationResult, FieldComparison
from app.views.analysis import (
    _calc_refund_deadline,
    build_analysis_result_blocks,
    build_cross_verification_blocks,
)


def _extract_all_text(blocks: list[dict]) -> str:
    """블록 내 모든 텍스트를 추출한다 (section text, fields, context)."""
    parts = []
    for b in blocks:
        if "text" in b and isinstance(b["text"], dict):
            parts.append(b["text"].get("text", ""))
        for f in b.get("fields", []):
            parts.append(f.get("text", ""))
        for e in b.get("elements", []):
            parts.append(e.get("text", ""))
    return "\n".join(parts)


class TestBuildAnalysisResultBlocks:
    def test_shows_document_type(self):
        result = AnalysisResult(
            document_type="항공사 운항정보확인서",
            extracted_fields={"날짜": "2025-12-13", "항공편": "KE123"},
            summary="대한항공 KE123편 결항 확인.",
        )
        blocks = build_analysis_result_blocks(result)
        header = blocks[0]["text"]["text"]
        assert "항공사 운항정보확인서" in header

    def test_shows_extracted_fields_as_grid(self):
        result = AnalysisResult(
            document_type="해운사 결항확인서",
            extracted_fields={"고객명": "홍길동", "날짜": "2025-12-13"},
        )
        blocks = build_analysis_result_blocks(result)
        has_fields = any("fields" in b for b in blocks)
        assert has_fields
        all_text = _extract_all_text(blocks)
        assert "홍길동" in all_text

    def test_shows_summary_in_context(self):
        result = AnalysisResult(
            document_type="항공사 운항정보확인서",
            summary="대한항공 KE123편이 기상악화로 결항.",
        )
        blocks = build_analysis_result_blocks(result)
        all_text = _extract_all_text(blocks)
        assert "대한항공" in all_text

    def test_refund_deadline_shown_when_date_exists(self):
        result = AnalysisResult(
            document_type="항공사 운항정보확인서",
            extracted_fields={"날짜": "2025-12-13", "항공편": "KE123"},
        )
        blocks = build_analysis_result_blocks(result)
        all_text = _extract_all_text(blocks)
        assert "환불 기한" in all_text
        assert "2026-01-12" in all_text

    def test_refund_deadline_not_shown_when_no_date(self):
        result = AnalysisResult(
            document_type="결항확인서",
            extracted_fields={"고객명": "홍길동"},
        )
        blocks = build_analysis_result_blocks(result)
        all_text = _extract_all_text(blocks)
        assert "환불 기한" not in all_text

    def test_null_document_type_shows_default(self):
        result = AnalysisResult(document_type=None, summary="내용 불명.")
        blocks = build_analysis_result_blocks(result)
        header = blocks[0]["text"]["text"]
        assert "문서" in header

    def test_empty_fields_no_grid(self):
        result = AnalysisResult(document_type="기타", extracted_fields={})
        blocks = build_analysis_result_blocks(result)
        has_fields = any("fields" in b for b in blocks)
        assert not has_fields


class TestCalcRefundDeadline:
    @pytest.mark.parametrize(
        ("date_str", "expected"),
        [
            ("2025-12-13", "2026-01-12"),
            ("2025.12.13", "2026-01-12"),
            ("2025/12/13", "2026-01-12"),
            ("2025년 12월 13일", "2026-01-12"),
        ],
    )
    def test_various_date_formats(self, date_str: str, expected: str):
        assert _calc_refund_deadline(date_str) == expected

    def test_unparseable_date_returns_none(self):
        assert _calc_refund_deadline("날짜불명") is None

    def test_empty_string_returns_none(self):
        assert _calc_refund_deadline("") is None


def _verification(
    verdict: str = "승인",
    reason: str = "모든 항목이 일치합니다.",
    comparisons: list[FieldComparison] | None = None,
    ai_used: bool = False,
    ai_reasoning: str = "",
) -> CrossVerificationResult:
    return CrossVerificationResult(
        verdict=verdict,
        reason=reason,
        field_comparisons=comparisons
        if comparisons is not None
        else [
            FieldComparison("고객명", "박성구", "박성구", "일치"),
            FieldComparison("예약번호", "OR2017576", "OR2017576", "일치"),
            FieldComparison("날짜", "2026-02-27", "2026-02-27~2026-03-02", "일치"),
        ],
        ai_used=ai_used,
        ai_reasoning=ai_reasoning,
    )


class TestBuildCrossVerificationBlocks:
    def test_승인_결과_블록(self):
        blocks = build_cross_verification_blocks(_verification(verdict="승인"))
        all_text = _extract_all_text(blocks)
        assert "large_green_circle" in all_text
        assert "승인" in all_text

    def test_반려_결과_블록(self):
        blocks = build_cross_verification_blocks(_verification(verdict="반려"))
        all_text = _extract_all_text(blocks)
        assert "red_circle" in all_text
        assert "반려" in all_text

    def test_보류_결과_블록(self):
        blocks = build_cross_verification_blocks(_verification(verdict="보류"))
        all_text = _extract_all_text(blocks)
        assert "large_yellow_circle" in all_text
        assert "보류" in all_text

    def test_판단사유_표시(self):
        blocks = build_cross_verification_blocks(
            _verification(reason="고객명이 불일치합니다.")
        )
        all_text = _extract_all_text(blocks)
        assert "고객명이 불일치합니다." in all_text

    def test_ai_판단시_추론_포함(self):
        blocks = build_cross_verification_blocks(
            _verification(ai_used=True, ai_reasoning="AI가 판단한 근거입니다.")
        )
        all_text = _extract_all_text(blocks)
        assert "AI가 판단한 근거입니다." in all_text

    def test_ai_미사용시_ai_추론_미표시(self):
        blocks = build_cross_verification_blocks(
            _verification(ai_used=False, ai_reasoning="표시되면 안 됨")
        )
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) == 1

    def test_빈_비교항목이면_fields_블록_없음(self):
        blocks = build_cross_verification_blocks(_verification(comparisons=[]))
        has_fields = any("fields" in b for b in blocks)
        assert not has_fields
