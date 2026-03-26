from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnalysisResult:
    """이미지 분석 결과."""

    extracted_fields: dict = field(default_factory=dict)
    summary: str = ""
    quality_issues: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Gemini가 판별한 부적합 사유가 없으면 유효."""
        return not self.rejection_reasons


@dataclass
class FieldComparison:
    """개별 필드 비교 결과."""

    field_name: str
    document_value: str
    reservation_value: str
    status: str  # "일치", "불일치", "확인불가", "비교불필요"
    note: str = ""


@dataclass
class CrossVerificationResult:
    """교차검증 최종 판단."""

    verdict: str  # "승인", "반려", "보류"
    reason: str
    field_comparisons: list[FieldComparison] = field(default_factory=list)
