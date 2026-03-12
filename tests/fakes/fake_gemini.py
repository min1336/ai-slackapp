from __future__ import annotations

from typing import Any


class FakeGeminiClient:
    """ImageAnalysisGateway Protocol 호환 Fake."""

    def __init__(self, result: dict[str, Any] | Exception | None = None) -> None:
        self.result = result
        self.calls: list[tuple[list[bytes], str]] = []

    def analyze_images(self, *, images: list[bytes], prompt: str) -> dict:
        self.calls.append((images, prompt))
        if isinstance(self.result, Exception):
            raise self.result
        if self.result is None:
            return {
                "is_valid": True,
                "confidence": 0.95,
                "document_type": "결항확인서",
                "extracted_fields": {},
                "mismatches": [],
                "quality_issues": [],
                "reasoning": "테스트 기본 응답",
            }
        return self.result
