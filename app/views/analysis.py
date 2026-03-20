from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.analysis import AnalysisResult, CrossVerificationResult

_PRIORITY_FIELDS = frozenset(
    {
        "고객명",
        "예약번호",
        "날짜",
        "항공편",
        "선편",
        "결항사유",
        "노선",
        "출발지",
        "도착지",
        "발급기관",
    }
)


def build_analysis_result_blocks(result: AnalysisResult) -> list[dict]:
    """분석 결과를 Block Kit blocks로 변환한다."""
    blocks: list[dict] = []

    # 헤더
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":page_facing_up: *결항확인서 분석 결과*",
            },
        }
    )

    # 추출 정보: 핵심 필드만 2열 fields 그리드
    if result.extracted_fields:
        fields = []
        for k, v in result.extracted_fields.items():
            if v and k in _PRIORITY_FIELDS:
                fields.append({"type": "mrkdwn", "text": f"*{k}*\n{v}"})
        for i in range(0, len(fields), 10):
            blocks.append({"type": "section", "fields": fields[i : i + 10]})

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
