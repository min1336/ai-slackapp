from __future__ import annotations

from slack_sdk.errors import SlackApiError

from app.infrastructure.slack_client import find_message_by_text


def _make_history_response(messages, next_cursor=""):
    return {
        "messages": messages,
        "response_metadata": {"next_cursor": next_cursor},
    }


class _FakeSlackClient:
    """find_message_by_text 테스트용 Fake WebClient stub.

    conversations_history()만 지원하며, 생성 시 전달한 응답 목록을
    호출 순서대로 반환한다.
    """

    def __init__(
        self,
        responses: list[dict] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._responses = responses or []
        self._error = error
        self.call_count = 0

    def conversations_history(self, **kwargs):
        self.call_count += 1
        if self._error:
            raise self._error
        idx = self.call_count - 1
        if idx < len(self._responses):
            return self._responses[idx]
        return {"messages": [], "response_metadata": {"next_cursor": ""}}


class _FakeSlackResponse:
    """SlackApiError 생성에 필요한 최소 응답 stub."""

    status_code = 500

    def __getattr__(self, _name):
        return ""

    def __str__(self):
        return "error"


class TestFindMessageByText:
    def test_첫_페이지에서_발견(self):
        client = _FakeSlackClient(
            [
                _make_history_response(
                    [
                        {"text": "다른 메시지", "ts": "111.111"},
                        {"text": "예약번호 BK-001 입니다", "ts": "222.222"},
                    ]
                )
            ]
        )

        result = find_message_by_text(client, "C123", "BK-001")
        assert result == "222.222"

    def test_두번째_페이지에서_발견(self):
        client = _FakeSlackClient(
            [
                _make_history_response(
                    [{"text": "관계없는 메시지", "ts": "111.111"}],
                    next_cursor="cursor_2",
                ),
                _make_history_response(
                    [{"text": "예약 BK-001 관련", "ts": "333.333"}],
                ),
            ]
        )

        result = find_message_by_text(client, "C123", "BK-001")
        assert result == "333.333"
        assert client.call_count == 2

    def test_max_pages_초과시_None(self):
        client = _FakeSlackClient(
            [
                _make_history_response(
                    [{"text": "무관한 메시지", "ts": "111.111"}],
                    next_cursor="more",
                ),
                _make_history_response(
                    [{"text": "무관한 메시지", "ts": "222.222"}],
                    next_cursor="more",
                ),
            ]
        )

        result = find_message_by_text(client, "C123", "BK-001", max_pages=2)
        assert result is None
        assert client.call_count == 2

    def test_빈_채널은_None(self):
        client = _FakeSlackClient([_make_history_response([])])

        result = find_message_by_text(client, "C123", "BK-001")
        assert result is None

    def test_SlackApiError_발생시_None(self):
        client = _FakeSlackClient(
            error=SlackApiError(
                message="error",
                response=_FakeSlackResponse(),
            ),
        )

        result = find_message_by_text(client, "C123", "BK-001")
        assert result is None

    def test_blocks_fields에서_발견(self):
        """Block Kit 메시지의 blocks[].fields[].text에서 검색어 발견."""
        client = _FakeSlackClient(
            [
                _make_history_response(
                    [
                        {
                            "text": "예약 정보를 확인해주세요",
                            "ts": "444.444",
                            "blocks": [
                                {
                                    "type": "section",
                                    "fields": [
                                        {"type": "mrkdwn", "text": "*예약번호*"},
                                        {"type": "plain_text", "text": "BK-001"},
                                    ],
                                }
                            ],
                        }
                    ]
                )
            ]
        )

        result = find_message_by_text(client, "C123", "BK-001")
        assert result == "444.444"

    def test_cursor_없으면_다음_페이지_요청_안함(self):
        client = _FakeSlackClient(
            [
                _make_history_response(
                    [{"text": "무관한 메시지", "ts": "111.111"}],
                ),
            ]
        )

        result = find_message_by_text(client, "C123", "BK-001")
        assert result is None
        assert client.call_count == 1
