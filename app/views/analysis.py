from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.analysis import AnalysisResult, CrossVerificationResult

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

    # 헤더: 문서유형
    doc_type = result.document_type or "문서"
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":page_facing_up: *{doc_type}*"},
        }
    )

    # 추출 정보: 2열 fields 그리드
    if result.extracted_fields:
        fields = []
        for k, v in result.extracted_fields.items():
            if v:
                fields.append({"type": "mrkdwn", "text": f"*{k}*\n{v}"})
        # 환불 기한
        cancel_date = result.extracted_fields.get("날짜", "")
        if cancel_date:
            deadline = _calc_refund_deadline(cancel_date)
            if deadline:
                fields.append({"type": "mrkdwn", "text": f"*환불 기한*\n~{deadline}"})
        if fields:
            blocks.append({"type": "section", "fields": fields[:10]})

    # 요약
    if result.summary:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": result.summary[:300]}],
            }
        )

    return blocks


_VERDICT_EMOJI = {
    "승인": ":large_green_circle:",
    "반려": ":red_circle:",
    "보류": ":large_yellow_circle:",
}

_STATUS_EMOJI = {
    "일치": "✓",
    "불일치": "✗",
    "확인불가": "?",
    "비교불필요": "—",
}


def build_cross_verification_blocks(result: CrossVerificationResult) -> list[dict]:
    """교차검증 결과를 Block Kit blocks로 변환한다."""
    blocks: list[dict] = []

    # 판정 결과
    emoji = _VERDICT_EMOJI.get(result.verdict, ":white_circle:")
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{emoji} *결항 신청 {result.verdict}*"},
        }
    )

    # 필드 비교 그리드
    if result.field_comparisons:
        fields = []
        for fc in result.field_comparisons:
            status_emoji = _STATUS_EMOJI.get(fc.status, fc.status)
            fields.append(
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*{fc.field_name}* {status_emoji} {fc.status}\n"
                        f"문서: {fc.document_value} / 예약: {fc.reservation_value}"
                    ),
                }
            )
        blocks.append({"type": "section", "fields": fields[:10]})

    # 판단 사유
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": result.reason}],
        }
    )

    # AI 추론 (ai_used=True이고 내용이 있을 때만)
    if result.ai_used and result.ai_reasoning:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": result.ai_reasoning}],
            }
        )

    return blocks
