from __future__ import annotations

import pytest

from app.models import SurveySubmission
from app.services.image_analyzer import ImageAnalyzer
from tests.fakes.fake_gemini import FakeGeminiClient

_VALID_RESPONSE = {
    "is_valid": True,
    "confidence": 0.95,
    "document_type": "결항확인서",
    "extracted_fields": {"고객명": "홍길동", "예약번호": "R12345"},
    "mismatches": [],
    "quality_issues": [],
    "reasoning": "문서 형식 및 내용이 적합합니다.",
}


def _submission(name: str = "홍길동", key: str = "R12345") -> SurveySubmission:
    return SurveySubmission(submission_id="1001", customer_name=name, booking_key=key)


class TestImageAnalyzerAnalyze:
    def test_valid_image_returns_valid_result(self):
        gemini = FakeGeminiClient(result=_VALID_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.is_valid is True
        assert result.confidence == 0.95
        assert result.document_type == "결항확인서"
        assert result.mismatches == []
        assert len(gemini.calls) == 1

    def test_invalid_image_returns_invalid_result(self):
        response = {
            **_VALID_RESPONSE,
            "is_valid": False,
            "mismatches": ["예약번호 불일치: 이미지(R99999) vs 제출(R12345)"],
            "reasoning": "예약번호가 일치하지 않습니다.",
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.is_valid is False
        assert len(result.mismatches) == 1

    def test_api_failure_raises(self):
        gemini = FakeGeminiClient(result=RuntimeError("API error"))
        analyzer = ImageAnalyzer(gemini)
        with pytest.raises(RuntimeError, match="API error"):
            analyzer.analyze([b"fake-png"], _submission())

    def test_malformed_response_returns_none_validity(self):
        gemini = FakeGeminiClient(result={"unexpected": "format"})
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.is_valid is None
        assert result.confidence == 0.0

    def test_oversized_image_filtered(self):
        gemini = FakeGeminiClient(result=_VALID_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        big_image = b"x" * (4 * 1024 * 1024 + 1)
        result = analyzer.analyze([big_image, b"small"], _submission())
        sent_images = gemini.calls[0][0]
        assert len(sent_images) == 1
        assert "이미지 크기 초과" in result.quality_issues[0]

    def test_max_10_images(self):
        gemini = FakeGeminiClient(result=_VALID_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        images = [b"img"] * 15
        analyzer.analyze(images, _submission())
        sent_images = gemini.calls[0][0]
        assert len(sent_images) == 10

    def test_all_images_oversized_returns_none_validity(self):
        gemini = FakeGeminiClient(result=_VALID_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        big = b"x" * (4 * 1024 * 1024 + 1)
        result = analyzer.analyze([big], _submission())
        assert result.is_valid is None
        assert len(gemini.calls) == 0

    def test_prompt_contains_submission_data(self):
        gemini = FakeGeminiClient(result=_VALID_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        analyzer.analyze([b"fake-png"], _submission(name="김철수", key="R99999"))
        prompt = gemini.calls[0][1]
        assert "김철수" in prompt
        assert "R99999" in prompt
