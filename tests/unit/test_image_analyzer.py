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

    def test_airline_doc_without_booking_key_is_valid(self):
        """항공사 운항정보확인서는 예약번호가 없어도 is_valid=True."""
        response = {
            "is_valid": True,
            "confidence": 0.90,
            "document_type": "항공사 운항정보확인서",
            "extracted_fields": {
                "고객명": "",
                "예약번호": "",
                "날짜": "2025-12-13",
                "항공편": "KE123",
                "결항사유": "기상악화",
                "발급기관": "대한항공",
            },
            "mismatches": [],
            "quality_issues": [],
            "reasoning": "항공사 발급 문서로 고객 정보 미기재는 정상.",
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.is_valid is True
        assert result.document_type == "항공사 운항정보확인서"
        assert result.mismatches == []

    def test_airline_doc_without_customer_name_is_valid(self):
        """항공사 운항정보확인서는 고객명이 없어도 is_valid=True."""
        response = {
            "is_valid": True,
            "confidence": 0.88,
            "document_type": "항공사 운항정보확인서",
            "extracted_fields": {
                "고객명": "",
                "예약번호": "",
                "날짜": "2025-12-13",
                "항공편": "OZ456",
                "결항사유": "운항 스케줄 변경",
                "발급기관": "아시아나항공",
            },
            "mismatches": [],
            "quality_issues": [],
            "reasoning": "항공사 운항정보확인서 — 고객 정보 미기재 정상.",
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.is_valid is True
        assert result.mismatches == []

    def test_maritime_doc_customer_name_mismatch_is_invalid(self):
        """해운사 결항확인서는 고객명 불일치 시 is_valid=False."""
        response = {
            "is_valid": False,
            "confidence": 0.85,
            "document_type": "해운사 결항확인서",
            "extracted_fields": {
                "고객명": "김영희",
                "예약번호": "R12345",
                "날짜": "2025-12-13",
                "항공편": "",
                "결항사유": "태풍",
                "발급기관": "한일고속",
            },
            "mismatches": ["고객명 불일치: 이미지(김영희) vs 제출(홍길동)"],
            "quality_issues": [],
            "reasoning": "고객명이 일치하지 않습니다.",
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.is_valid is False
        assert len(result.mismatches) == 1

    def test_non_cancellation_doc_is_invalid(self):
        """결항확인서가 아닌 문서는 is_valid=False."""
        response = {
            "is_valid": False,
            "confidence": 0.92,
            "document_type": "기타",
            "extracted_fields": {},
            "mismatches": [],
            "quality_issues": [],
            "reasoning": "결항확인서가 아닌 일반 영수증입니다.",
        }
        gemini = FakeGeminiClient(result=response)
        analyzer = ImageAnalyzer(gemini)
        result = analyzer.analyze([b"fake-png"], _submission())
        assert result.is_valid is False
        assert result.document_type == "기타"
