from __future__ import annotations

from app.models.analysis import AnalysisResult
from app.views.analysis import build_analysis_result_blocks


class TestBuildAnalysisResultBlocks:
    def test_valid_result_shows_checkmark(self):
        result = AnalysisResult(
            is_valid=True,
            confidence=0.95,
            document_type="결항확인서",
            extracted_fields={"고객명": "홍길동", "예약번호": "R12345"},
            reasoning="문서 형식 적합",
        )
        blocks = build_analysis_result_blocks(result)
        text = blocks[0]["text"]["text"]
        assert "검증 완료" in text

    def test_invalid_result_shows_mismatches(self):
        result = AnalysisResult(
            is_valid=False,
            confidence=0.8,
            document_type="결항확인서",
            mismatches=["예약번호 불일치"],
            reasoning="예약번호가 일치하지 않습니다.",
        )
        blocks = build_analysis_result_blocks(result)
        text = blocks[0]["text"]["text"]
        assert "부적합" in text
        full_text = "".join(b.get("text", {}).get("text", "") for b in blocks)
        assert "예약번호 불일치" in full_text

    def test_none_validity_shows_warning(self):
        result = AnalysisResult(
            is_valid=None,
            confidence=0.0,
            document_type=None,
            reasoning="분석 실패",
        )
        blocks = build_analysis_result_blocks(result)
        text = blocks[0]["text"]["text"]
        assert "분석 실패" in text or "판단 불가" in text
