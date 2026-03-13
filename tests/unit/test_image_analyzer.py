from __future__ import annotations

import pytest

from app.models import SurveySubmission
from app.services.image_analyzer import ImageAnalyzer
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
