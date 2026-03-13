from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.analysis import AnalysisResult

_REFUND_DEADLINE_DAYS = 30

_DATE_FORMATS = ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y년 %m월 %d일")


def _parse_date(raw: str) -> datetime | None:
    """다양한 형식의 날짜 문자열을 파싱한다."""
    stripped = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt)
        except ValueError:
            continue
    return None


def _calc_refund_deadline(date_str: str) -> str | None:
    """결항 날짜에서 환불 기한(+30일)을 계산한다."""
    dt = _parse_date(date_str)
    if dt is None:
        return None
    deadline = dt + timedelta(days=_REFUND_DEADLINE_DAYS)
    return deadline.strftime("%Y-%m-%d")


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
        # 환불 기한 계산
        cancel_date = result.extracted_fields.get("날짜", "")
        if cancel_date:
            deadline = _calc_refund_deadline(cancel_date)
            if deadline:
                fields_text += f"\n- 환불 신청 기한: ~{deadline}"
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
