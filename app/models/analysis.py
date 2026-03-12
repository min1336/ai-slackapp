from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnalysisResult:
    """이미지 분석 결과."""

    is_valid: bool | None
    confidence: float
    document_type: str | None
    extracted_fields: dict = field(default_factory=dict)
    mismatches: list[str] = field(default_factory=list)
    quality_issues: list[str] = field(default_factory=list)
    reasoning: str = ""
