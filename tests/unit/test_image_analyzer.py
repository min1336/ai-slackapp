from __future__ import annotations

import pytest

from app.models import SurveySubmission
from app.models.analysis import AnalysisResult
from app.services.image_analyzer import ImageAnalyzer
from app.views.analysis import build_analysis_result_blocks
from tests.fakes.fake_gemini import FakeGeminiClient

_SAMPLE_RESPONSE = {
    "extracted_fields": {
        "고객명": "홍길동",
        "예약번호": "R12345",
        "날짜": "2025-12-13",
        "항공편": "KE123",
        "결항사유": "기상악화",
        "발급기관": "대한항공",
    },
    "summary": "대한항공 KE123편이 2025-12-13 기상악화로 결항.",
}


def _submission(name: str = "홍길동", key: str = "R12345") -> SurveySubmission:
    return SurveySubmission(submission_id="1001", customer_name=name, booking_key=key)


class TestImageAnalyzerAnalyze:
    def test_returns_extracted_fields(self):
        gemini = FakeGeminiClient(result=_SAMPLE_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.extracted_fields["항공편"] == "KE123"
        assert "기상악화" in result.summary
        assert len(gemini.calls) == 1

    def test_other_doc_type(self):
        response = {
            "extracted_fields": {},
            "summary": "결항확인서가 아닌 일반 영수증.",
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert "영수증" in result.summary

    def test_api_failure_raises(self):
        gemini = FakeGeminiClient(result=RuntimeError("API error"))
        analyzer = ImageAnalyzer(gemini)
        with pytest.raises(RuntimeError, match="API error"):
            analyzer.analyze([b"fake-png"], _submission())

    def test_malformed_response_returns_fallback(self):
        gemini = FakeGeminiClient(result={"unexpected": "format"})
        analyzer = ImageAnalyzer(gemini)
        analyzer.analyze([b"fake-png"], _submission())

    def test_oversized_image_filtered(self):
        gemini = FakeGeminiClient(result=_SAMPLE_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        big_image = b"x" * (4 * 1024 * 1024 + 1)
        result = analyzer.analyze([big_image, b"small"], _submission())
        sent_images = gemini.calls[0][0]
        assert len(sent_images) == 1
        assert "이미지 크기 초과" in result.quality_issues[0]

    def test_max_10_images(self):
        gemini = FakeGeminiClient(result=_SAMPLE_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        images = [b"img"] * 15
        analyzer.analyze(images, _submission())
        sent_images = gemini.calls[0][0]
        assert len(sent_images) == 10

    def test_all_images_oversized_returns_no_summary(self):
        gemini = FakeGeminiClient(result=_SAMPLE_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        big = b"x" * (4 * 1024 * 1024 + 1)
        result = analyzer.analyze([big], _submission())
        assert "분석 가능한 이미지가 없습니다" in result.summary
        assert len(gemini.calls) == 0

    def test_list_response_normalized_to_first_element(self):
        response = [
            {
                "extracted_fields": {"고객명": "홍길동"},
                "summary": "첫 번째 문서",
            },
            {
                "extracted_fields": {"고객명": "김영희"},
                "summary": "두 번째 문서",
            },
        ]
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"img1", b"img2"], _submission())
        assert result.extracted_fields["고객명"] == "홍길동"

    def test_empty_list_response_returns_fallback(self):
        gemini = FakeGeminiClient(result=[])
        analyzer = ImageAnalyzer(gemini)
        analyzer.analyze([b"img"], _submission())

    def test_rejection_reasons_파싱(self):
        response = {
            "extracted_fields": {"고객명": "홍길동"},
            "summary": "문서 요약",
            "rejection_reasons": ["흐린 이미지"],
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.rejection_reasons == ["흐린 이미지"]
        assert not result.is_valid

    def test_rejection_reasons_빈배열이면_valid(self):
        response = {
            "extracted_fields": {},
            "summary": "정상 문서",
            "rejection_reasons": [],
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.rejection_reasons == []
        assert result.is_valid

    def test_rejection_reasons_없으면_기본값_valid(self):
        gemini = FakeGeminiClient(result=_SAMPLE_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.rejection_reasons == []
        assert result.is_valid

    def test_rejection_reasons_문자열이면_빈리스트로_정규화(self):
        response = {
            "extracted_fields": {},
            "summary": "문서 요약",
            "rejection_reasons": "문자열로 왔음",
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.rejection_reasons == []
        assert result.is_valid

    def test_maritime_doc_extracts_fields(self):
        response = {
            "extracted_fields": {
                "고객명": "김영희",
                "날짜": "2025-12-13",
                "결항사유": "태풍",
                "발급기관": "한일고속",
            },
            "summary": "한일고속 2025-12-13 태풍으로 결항.",
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.extracted_fields["결항사유"] == "태풍"


class TestDocumentConsistency:
    """여러 문서 간 정보 일관성 검증 테스트."""

    def test_프롬프트에_GDS_날짜_형식_가이드_포함(self):
        """AI 프롬프트에 항공 GDS 날짜(DDMmmYY) 파싱 가이드가 포함되어야 한다."""
        from app.services.image_analyzer import _ANALYSIS_PROMPT

        assert "DDMmmYY" in _ANALYSIS_PROMPT
        assert "18MAR26" in _ANALYSIS_PROMPT

    def test_문서간_날짜_불일치_rejection(self):
        """두 문서에서 동일 항공편의 결항 날짜가 상이하면 is_valid=False."""
        response = {
            "extracted_fields": {
                "고객명": "홍길동",
                "항공편": "OZ8197",
                "날짜": "2018-03-26",
                "결항사유": "기상악화",
                "발급기관": "아시아나항공",
            },
            "summary": "아시아나 OZ8197편 결항 확인서",
            "rejection_reasons": [
                "제출된 두 문서에서 동일 항공편(OZ8197)의 결항 날짜가 "
                "2018년 3월 26일과 2018년 3월 18일로 상이"
            ],
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"img1", b"img2"], _submission())

        assert not result.is_valid
        assert len(result.rejection_reasons) == 1
        assert "상이" in result.rejection_reasons[0]

    def test_문서간_편명_불일치_rejection(self):
        """두 문서에서 항공편 번호가 다르면 is_valid=False."""
        response = {
            "extracted_fields": {
                "고객명": "김철수",
                "항공편": "KE123",
                "날짜": "2026-01-15",
                "결항사유": "기상악화",
            },
            "summary": "편명 불일치 문서",
            "rejection_reasons": [
                "문서 1의 항공편(KE123)과 문서 2의 항공편(OZ456)이 상이"
            ],
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"img1", b"img2"], _submission())

        assert not result.is_valid
        assert "상이" in result.rejection_reasons[0]

    def test_문서간_다중_불일치_모두_포함(self):
        """날짜 + 편명 등 여러 불일치가 모두 rejection_reasons에 포함."""
        response = {
            "extracted_fields": {"고객명": "홍길동", "날짜": "2026-01-15"},
            "summary": "다중 불일치",
            "rejection_reasons": [
                "동일 항공편의 날짜가 문서 간 상이",
                "항공편 번호가 문서 간 상이",
            ],
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"img1", b"img2"], _submission())

        assert not result.is_valid
        assert len(result.rejection_reasons) == 2


class TestAnalysisResultBlocks:
    def test_날짜_필드_표시(self):
        result = AnalysisResult(
            extracted_fields={"고객명": "홍길동", "날짜": "2026-02-24"},
        )
        blocks = build_analysis_result_blocks(result)
        all_text = str(blocks)
        assert "홍길동" in all_text
        assert "2026-02-24" in all_text
        assert "환불 기한" not in all_text
