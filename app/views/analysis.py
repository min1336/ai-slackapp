from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.analysis import AnalysisResult


def build_analysis_result_blocks(result: AnalysisResult) -> list[dict]:
    """분석 결과를 Block Kit blocks로 변환한다."""
    blocks: list[dict] = []

    if result.is_valid is True:
        header = f":white_check_mark: *검증 완료* (신뢰도: {result.confidence:.0%})"
    elif result.is_valid is False:
        header = f":x: *부적합* (신뢰도: {result.confidence:.0%})"
    else:
        header = ":warning: *판단 불가*"

    if result.document_type:
        header += f"\n문서 유형: {result.document_type}"

    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": header}})

    if result.extracted_fields:
        fields_text = "\n".join(
            f"- {k}: {v}" for k, v in result.extracted_fields.items() if v
        )
        if fields_text:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*추출 정보*\n{fields_text}"},
                }
            )

    if result.mismatches:
        mismatch_text = "\n".join(f"- {m}" for m in result.mismatches)
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*불일치 항목*\n{mismatch_text}"},
            }
        )

    if result.quality_issues:
        issues_text = "\n".join(f"- {q}" for q in result.quality_issues)
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*품질 이슈*\n{issues_text}"},
            }
        )

    if result.reasoning:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": result.reasoning[:300]}],
            }
        )

    return blocks
