from __future__ import annotations

from typing import Any


class FakeGeminiClient:
    """ImageAnalysisGateway Protocol 호환 Fake."""

    def __init__(self, result: dict[str, Any] | list | Exception | None = None) -> None:
        self.result = result
        self.calls: list[tuple[list[bytes], str]] = []

    def analyze_images(self, *, images: list[bytes], prompt: str) -> dict:
        self.calls.append((images, prompt))
        if isinstance(self.result, Exception):
            raise self.result
        if self.result is None:
            return {
                "extracted_fields": {},
                "summary": "테스트 기본 응답",
                "rejection_reasons": [],
            }
        return self.result
