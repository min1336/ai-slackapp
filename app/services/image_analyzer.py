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
예약번호 {booking_key} (고객명: {customer_name})에 대한 결항확인 증빙 이미지입니다.
이미지에서 정보를 추출하고 요약해주세요.

## 작업

1. 문서 유형을 분류하세요:
   - "항공사 운항정보확인서": 항공사가 발급한 운항 변경/결항 확인 문서
   - "해운사 결항확인서": 해운사/선사가 발급한 결항 확인 문서
   - "기타": 위에 해당하지 않는 문서
2. 문서에서 읽을 수 있는 모든 정보를 key-value 형태로 추출하세요.
   다음 핵심 필드는 해당 key 이름으로 반드시 포함 (읽을 수 없으면 빈 문자열):
   고객명, 예약번호, 날짜, 항공편, 결항사유, 발급기관.
   그 외 문서에 표시된 모든 정보(노선, 출발시각, 대체편, PNR/확인번호, 발급일 등)도
   적절한 key를 지어 추출하세요.
3. 추출한 정보를 바탕으로 문서 내용을 1~2문장으로 요약하세요.
4. 문서의 유효성을 검증하세요. 다음 중 해당하는 문제가 있으면 rejection_reasons에 추가:
   - 이미지가 흐리거나 텍스트를 읽을 수 없는 경우
   - 결항이 아닌 지연(delay) 안내 문서인 경우
   - 문서가 위조/변조된 것으로 의심되는 경우
   - 고객명, 항공편/선편 번호, 날짜 등 핵심 정보가 누락된 경우
   - 문서에 표시된 고객명이 제출된 고객명({customer_name})과 명백히 다른 경우
   주의: 예약번호는 렌트카 예약번호와 항공/선박 예약번호가
   다른 시스템이므로 비교하지 마세요.

## 응답 형식

여러 이미지가 있더라도 하나의 JSON 객체로 통합하여 응답하세요.
반드시 아래 JSON 형식으로만 응답하세요 (배열이 아닌 단일 객체):
{{
  "document_type": "항공사 운항정보확인서" | "해운사 결항확인서" | "기타" | null,
  "extracted_fields": {{
    "고객명": "...", "예약번호": "...", "날짜": "...",
    "항공편": "...", "결항사유": "...", "발급기관": "...",
    "...그 외 읽을 수 있는 모든 필드": "..."
  }},
  "summary": "문서 내용 요약",
  "rejection_reasons": []
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

        logger.info(
            "image_filter_result",
            original_count=len(image_bytes_list),
            filtered_count=len(filtered),
            quality_issues=quality_issues or None,
            original_sizes=[len(img) for img in image_bytes_list],
            filtered_sizes=[len(img) for img in filtered],
        )

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
        raw = self._normalize_response(raw)
        logger.debug(
            "gemini_raw_response",
            raw_keys=list(raw.keys()),
            document_type=raw.get("document_type"),
        )
        result = self._parse_response(raw, quality_issues)
        logger.info(
            "analysis_result",
            document_type=result.document_type,
            is_valid=result.is_valid,
            extracted_fields=result.extracted_fields,
            summary=result.summary[:200] if result.summary else "",
        )
        return result

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
    def _normalize_response(raw: dict | list) -> dict:
        """배열 응답을 단일 dict로 정규화한다."""
        if isinstance(raw, list):
            logger.warning(
                "gemini_response_normalized",
                original_type="list",
                length=len(raw),
            )
            return raw[0] if raw else {}
        return raw

    @staticmethod
    def _parse_response(raw: dict, extra_issues: list[str]) -> AnalysisResult:
        try:
            rejection = raw.get("rejection_reasons", [])
            if not isinstance(rejection, list):
                rejection = []
            result = AnalysisResult(
                document_type=raw.get("document_type"),
                extracted_fields=raw.get("extracted_fields", {}),
                summary=raw.get("summary", ""),
                quality_issues=extra_issues,
                rejection_reasons=rejection,
            )
        except (TypeError, ValueError, AttributeError):
            logger.warning("gemini_response_parse_failed", raw=raw)
            result = AnalysisResult(
                document_type=None,
                quality_issues=extra_issues,
                summary="응답 파싱 실패",
            )
        return result
