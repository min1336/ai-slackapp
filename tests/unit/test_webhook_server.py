from __future__ import annotations

from urllib.parse import urlencode

from app.listener.webhook import extract_submission_id


class TestExtractSubmissionId:
    def test_urlencoded_body에서_추출(self):
        body = urlencode({"submissionID": "5001", "rawRequest": "{}"}).encode()
        assert extract_submission_id(body) == "5001"

    def test_잘못된_body_None_반환(self):
        assert extract_submission_id(b"garbage data") is None

    def test_submissionID_없으면_None(self):
        body = urlencode({"rawRequest": "{}"}).encode()
        assert extract_submission_id(body) is None

    def test_multipart_body에서_추출(self):
        boundary = "----TestBoundary"
        content_type = f"multipart/form-data; boundary={boundary}"
        body = (
            b"------TestBoundary\r\n"
            b'Content-Disposition: form-data; name="submissionID"\r\n\r\n'
            b"12345\r\n"
            b"------TestBoundary--\r\n"
        )
        assert extract_submission_id(body, content_type) == "12345"

    def test_multipart_submissionID_없으면_None(self):
        boundary = "----TestBoundary"
        content_type = f"multipart/form-data; boundary={boundary}"
        body = (
            b"------TestBoundary\r\n"
            b'Content-Disposition: form-data; name="formID"\r\n\r\n'
            b"99999\r\n"
            b"------TestBoundary--\r\n"
        )
        assert extract_submission_id(body, content_type) is None
