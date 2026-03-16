from __future__ import annotations

import pytest

from app.models import SurveySubmission
from app.models.analysis import AnalysisResult
from app.services.image_analyzer import ImageAnalyzer
from app.views.analysis import build_analysis_result_blocks
from tests.fakes.fake_gemini import FakeGeminiClient

_SAMPLE_RESPONSE = {
    "document_type": "항공사 운항정보확인서",
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
        assert result.document_type == "항공사 운항정보확인서"
        assert result.extracted_fields["항공편"] == "KE123"
        assert "기상악화" in result.summary
        assert len(gemini.calls) == 1

    def test_other_doc_type(self):
        response = {
            "document_type": "기타",
            "extracted_fields": {},
            "summary": "결항확인서가 아닌 일반 영수증.",
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.document_type == "기타"
        assert "영수증" in result.summary

    def test_api_failure_raises(self):
        gemini = FakeGeminiClient(result=RuntimeError("API error"))
        analyzer = ImageAnalyzer(gemini)
        with pytest.raises(RuntimeError, match="API error"):
            analyzer.analyze([b"fake-png"], _submission())

    def test_malformed_response_returns_fallback(self):
        gemini = FakeGeminiClient(result={"unexpected": "format"})
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.document_type is None

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
        assert result.document_type is None
        assert "분석 가능한 이미지가 없습니다" in result.summary
        assert len(gemini.calls) == 0

    def test_list_response_normalized_to_first_element(self):
        response = [
            {
                "document_type": "항공사 운항정보확인서",
                "extracted_fields": {"고객명": "홍길동"},
                "summary": "첫 번째 문서",
            },
            {
                "document_type": "해운사 결항확인서",
                "extracted_fields": {"고객명": "김영희"},
                "summary": "두 번째 문서",
            },
        ]
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"img1", b"img2"], _submission())
        assert result.document_type == "항공사 운항정보확인서"
        assert result.extracted_fields["고객명"] == "홍길동"

    def test_empty_list_response_returns_fallback(self):
        gemini = FakeGeminiClient(result=[])
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"img"], _submission())
        assert result.document_type is None

    def test_rejection_reasons_파싱(self):
        response = {
            "document_type": "항공사 운항정보확인서",
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
            "document_type": "항공사 운항정보확인서",
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
            "document_type": "항공사 운항정보확인서",
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
            "document_type": "해운사 결항확인서",
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
        assert result.document_type == "해운사 결항확인서"
        assert result.extracted_fields["결항사유"] == "태풍"


class TestAnalysisResultBlocks:
    def test_파싱불가_날짜_환불기한_생략(self):
        result = AnalysisResult(
            document_type="항공사 운항정보확인서",
            extracted_fields={"고객명": "홍길동", "날짜": "어제"},
        )
        blocks = build_analysis_result_blocks(result)
        all_text = str(blocks)
        assert "환불 기한" not in all_text
        assert "홍길동" in all_text  # 고객명은 _PRIORITY_FIELDS에 포함

    def test_정상_날짜_환불기한_표시(self):
        result = AnalysisResult(
            document_type="항공사 운항정보확인서",
            extracted_fields={"날짜": "2026-02-24"},
        )
        blocks = build_analysis_result_blocks(result)
        all_text = str(blocks)
        assert "환불 기한" in all_text
        assert "2026-03-26" in all_text
