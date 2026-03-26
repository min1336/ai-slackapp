from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.analysis import AnalysisResult

_PRIORITY_FIELDS = (
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

    # 핵심 필드 — 고정 순서, 2열 그리드, `라벨` 값 포맷
    if result.extracted_fields:
        fields = []
        for key in _PRIORITY_FIELDS:
            value = result.extracted_fields.get(key)
            if value:
                fields.append({"type": "mrkdwn", "text": f"`{key}` {value}"})
        if fields:
            blocks.append({"type": "divider"})
            for i in range(0, len(fields), 10):
                blocks.append({"type": "section", "fields": fields[i : i + 10]})

    # 요약
    if result.summary:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": result.summary},
            }
        )

    # 품질 이슈
    if result.quality_issues:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "\u26a0\ufe0f "
                        + " \u00b7 ".join(result.quality_issues),
                    }
                ],
            }
        )

    return blocks
