from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.analysis import AnalysisResult

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
