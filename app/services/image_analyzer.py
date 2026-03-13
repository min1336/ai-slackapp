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
이미지에서 정보를 추출하고 요약해주세요.

## 작업

1. 문서 유형을 분류하세요:
   - "항공사 운항정보확인서": 항공사가 발급한 운항 변경/결항 확인 문서
   - "해운사 결항확인서": 해운사/선사가 발급한 결항 확인 문서
   - "기타": 위에 해당하지 않는 문서
2. 다음 정보를 최대한 추출하세요:
   고객명, 예약번호, 날짜, 항공편/선편, 결항사유, 발급기관.
3. 추출한 정보를 바탕으로 문서 내용을 1~2문장으로 요약하세요.

## 응답 형식

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "document_type": "항공사 운항정보확인서" | "해운사 결항확인서" | "기타" | null,
  "extracted_fields": {{
    "고객명": "...", "예약번호": "...", "날짜": "...",
    "항공편": "...", "결항사유": "...", "발급기관": "..."
  }},
  "summary": "문서 내용 요약"
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
                document_type=None,
                quality_issues=quality_issues,
                summary="분석 가능한 이미지가 없습니다.",
            )

        prompt = _ANALYSIS_PROMPT.format(
            customer_name=submission.customer_name,
            booking_key=submission.booking_key,
        )

        raw = self._gateway.analyze_images(images=filtered, prompt=prompt)
        logger.debug(
            "gemini_raw_response",
            raw_keys=list(raw.keys()),
            document_type=raw.get("document_type"),
        )
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
                document_type=raw.get("document_type"),
                extracted_fields=raw.get("extracted_fields", {}),
                summary=raw.get("summary", ""),
                quality_issues=extra_issues,
            )
        except (TypeError, ValueError, AttributeError):
            logger.warning("gemini_response_parse_failed", raw=raw)
            result = AnalysisResult(
                document_type=None,
                quality_issues=extra_issues,
                summary="응답 파싱 실패",
            )
        return result
