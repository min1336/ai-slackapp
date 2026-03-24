from __future__ import annotations

from app.models.analysis import AnalysisResult
from app.views.analysis import build_analysis_result_blocks


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
    def test_shows_extracted_fields_as_grid(self):
        result = AnalysisResult(
            extracted_fields={"고객명": "홍길동", "날짜": "2025-12-13"},
        )
        blocks = build_analysis_result_blocks(result)
        has_fields = any("fields" in b for b in blocks)
        assert has_fields
        all_text = _extract_all_text(blocks)
        assert "홍길동" in all_text

    def test_shows_summary_in_context(self):
        result = AnalysisResult(
            summary="대한항공 KE123편이 기상악화로 결항.",
        )
        blocks = build_analysis_result_blocks(result)
        all_text = _extract_all_text(blocks)
        assert "대한항공" in all_text

    def test_empty_fields_no_grid(self):
        result = AnalysisResult(extracted_fields={})
        blocks = build_analysis_result_blocks(result)
        has_fields = any("fields" in b for b in blocks)
        assert not has_fields
