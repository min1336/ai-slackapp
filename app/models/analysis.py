from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnalysisResult:
    """이미지 분석 결과."""

    document_type: str | None
    extracted_fields: dict = field(default_factory=dict)
    summary: str = ""
    quality_issues: list[str] = field(default_factory=list)
