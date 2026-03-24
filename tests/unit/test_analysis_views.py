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


def _blocks_of_type(blocks: list[dict], block_type: str) -> list[dict]:
    return [b for b in blocks if b.get("type") == block_type]


class TestBuildAnalysisResultBlocks:
    def test_priority_fields_use_code_label_format(self):
        """`라벨` 값 포맷으로 표시된다."""
        result = AnalysisResult(
            extracted_fields={"고객명": "홍길동", "날짜": "2025-12-13"},
        )
        blocks = build_analysis_result_blocks(result)
        all_text = _extract_all_text(blocks)
        assert "`고객명` 홍길동" in all_text
        assert "`날짜` 2025-12-13" in all_text

    def test_priority_fields_in_fixed_order(self):
        """dict 삽입 순서와 무관하게 고정 순서로 표시된다."""
        result = AnalysisResult(
            extracted_fields={
                "발급기관": "대한항공",
                "고객명": "홍길동",
                "항공편": "KE123",
            },
        )
        blocks = build_analysis_result_blocks(result)
        field_texts = []
        for b in blocks:
            for f in b.get("fields", []):
                field_texts.append(f["text"])

        idx_customer = next(i for i, t in enumerate(field_texts) if "고객명" in t)
        idx_flight = next(i for i, t in enumerate(field_texts) if "항공편" in t)
        idx_issuer = next(i for i, t in enumerate(field_texts) if "발급기관" in t)
        assert idx_customer < idx_flight < idx_issuer

    def test_summary_not_rendered(self):
        """요약은 블록에 포함되지 않는다."""
        result = AnalysisResult(
            extracted_fields={"고객명": "홍길동"},
            summary="KE123편이 기상악화로 결항.",
        )
        blocks = build_analysis_result_blocks(result)
        all_text = _extract_all_text(blocks)
        assert "기상악화" not in all_text

    def test_quality_issues_displayed(self):
        """quality_issues가 있으면 표시된다."""
        result = AnalysisResult(
            extracted_fields={"고객명": "홍길동"},
            quality_issues=["이미지 크기 초과"],
        )
        blocks = build_analysis_result_blocks(result)
        all_text = _extract_all_text(blocks)
        assert "이미지 크기 초과" in all_text

    def test_quality_issues_hidden_when_empty(self):
        result = AnalysisResult(
            extracted_fields={"고객명": "홍길동"},
            quality_issues=[],
        )
        blocks = build_analysis_result_blocks(result)
        all_text = _extract_all_text(blocks)
        assert "\u26a0" not in all_text

    def test_divider_between_header_and_fields(self):
        """헤더와 필드 사이에 divider가 있다."""
        result = AnalysisResult(
            extracted_fields={"고객명": "홍길동"},
        )
        blocks = build_analysis_result_blocks(result)
        dividers = _blocks_of_type(blocks, "divider")
        assert len(dividers) == 1

    def test_empty_fields_no_grid(self):
        result = AnalysisResult(extracted_fields={})
        blocks = build_analysis_result_blocks(result)
        has_fields = any("fields" in b for b in blocks)
        assert not has_fields
