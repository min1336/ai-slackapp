from __future__ import annotations

from typing import TYPE_CHECKING

from app.core import get_logger
from app.models.analysis import AnalysisResult

if TYPE_CHECKING:
    from app.infrastructure.protocols import ImageAnalysisGateway
    from app.models import SurveySubmission

logger = get_logger(__name__)

_MAX_IMAGE_SIZE = 4 * 1024 * 1024  # 4MB
_MAX_IMAGE_COUNT = 10

_ANALYSIS_PROMPT = """\
당신은 항공/선박 결항확인서를 검증하는 전문가입니다.

## 작업

1. 이미지가 결항확인서인지 판단하세요.
2. 이미지 품질을 평가하세요 (텍스트 판독 가능 여부).
3. 다음 정보를 추출하세요: 고객명, 예약번호, 날짜, 항공편/선편, 결항 사유, 발급 기관.
4. 추출한 정보를 아래 제출 데이터와 대조하세요:
   - 고객명: {customer_name}
   - 예약번호: {booking_key}
5. 문서의 전반적 신뢰도를 평가하세요 (날짜 일관성, 항공편 형식, 결항 사유의 합리성).

## 응답 형식

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "is_valid": true | false | null,
  "confidence": 0.0~1.0,
  "document_type": "결항확인서" | "기타" | null,
  "extracted_fields": {{
    "고객명": "...", "예약번호": "...", "날짜": "...",
    "항공편": "...", "결항사유": "...", "발급기관": "..."
  }},
  "mismatches": ["불일치 항목 설명"],
  "quality_issues": ["품질 문제 설명"],
  "reasoning": "판단 근거 요약"
}}
"""


class ImageAnalyzer:
    """이미지 분석 컴포넌트. 프롬프트 구성 + 응답 파싱."""

    def __init__(self, gateway: ImageAnalysisGateway) -> None:
        self._gateway = gateway

    def analyze(
        self, image_bytes_list: list[bytes], submission: SurveySubmission
    ) -> AnalysisResult:
        filtered, quality_issues = self._filter_images(image_bytes_list)

        if not filtered:
            return AnalysisResult(
                is_valid=None,
                confidence=0.0,
                document_type=None,
                quality_issues=quality_issues,
                reasoning="분석 가능한 이미지가 없습니다.",
            )

        prompt = _ANALYSIS_PROMPT.format(
            customer_name=submission.customer_name,
            booking_key=submission.booking_key,
        )

        raw = self._gateway.analyze_images(images=filtered, prompt=prompt)
        return self._parse_response(raw, quality_issues)

    def _filter_images(self, images: list[bytes]) -> tuple[list[bytes], list[str]]:
        quality_issues: list[str] = []
        filtered: list[bytes] = []

        for i, img in enumerate(images):
            if len(img) > _MAX_IMAGE_SIZE:
                quality_issues.append(
                    f"이미지 크기 초과: 이미지 {i + 1} ({len(img)} bytes)"
                )
                continue
            filtered.append(img)

        if len(filtered) > _MAX_IMAGE_COUNT:
            quality_issues.append(
                f"이미지 수 제한: {len(filtered)}장 중 {_MAX_IMAGE_COUNT}장만 분석"
            )
            filtered = filtered[:_MAX_IMAGE_COUNT]

        return filtered, quality_issues

    @staticmethod
    def _parse_response(raw: dict, extra_issues: list[str]) -> AnalysisResult:
        try:
            result = AnalysisResult(
                is_valid=raw.get("is_valid"),
                confidence=float(raw.get("confidence", 0.0)),
                document_type=raw.get("document_type"),
                extracted_fields=raw.get("extracted_fields", {}),
                mismatches=raw.get("mismatches", []),
                quality_issues=raw.get("quality_issues", []) + extra_issues,
                reasoning=raw.get("reasoning", ""),
            )
        except (TypeError, ValueError, AttributeError):
            result = AnalysisResult(
                is_valid=None,
                confidence=0.0,
                document_type=None,
                quality_issues=extra_issues,
                reasoning="응답 파싱 실패",
            )
        return result
