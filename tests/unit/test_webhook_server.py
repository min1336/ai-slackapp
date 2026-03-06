from __future__ import annotations

import json
from urllib.parse import urlencode

from app.listener.webhook import parse_jotform_post_body


class TestParseJotformPostBody:
    def test_urlencoded_rawRequest_파싱(self):
        raw = json.dumps(
            {
                "12": {"answer": "홍길동"},
                "14": {"answer": "R12345"},
                "26": {"answer": "업체A"},
                "13": {"answer": {"full": "010-0000-0000"}},
                "11": {"answer": ["https://jotform.com/file.jpg"]},
            }
        )
        body = urlencode({"submissionID": "5001", "rawRequest": raw}).encode()
        result = parse_jotform_post_body(body)

        assert result is not None
        sub, file_urls = result
        assert sub.submission_id == "5001"
        assert sub.booking_key == "R12345"
        assert sub.customer_name == "홍길동"
        assert file_urls == ["https://jotform.com/file.jpg"]

    def test_잘못된_body_None_반환(self):
        result = parse_jotform_post_body(b"garbage data")
        assert result is None

    def test_submissionID_없으면_None(self):
        raw = json.dumps({"12": {"answer": "테스트"}})
        body = urlencode({"rawRequest": raw}).encode()
        result = parse_jotform_post_body(body)
        assert result is None

    def test_rawRequest_없으면_None(self):
        body = urlencode({"submissionID": "123"}).encode()
        result = parse_jotform_post_body(body)
        assert result is None
