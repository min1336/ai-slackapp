from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from urllib.parse import urlencode

import pytest

from app.listener.webhook import _WebhookHandler, extract_submission_id
from app.models import SurveySubmission


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


@pytest.fixture()
def webhook_server(monkeypatch):
    """테스트용 webhook 서버를 임의 포트로 시작하고 종료한다."""
    stub_sub = SurveySubmission(submission_id="stub", customer_name="", booking_key="")
    monkeypatch.setattr("app.listener.webhook.fetch_jotform_submission", lambda *a: {})
    monkeypatch.setattr(
        "app.listener.webhook.parse_jotform_answers", lambda *a: (stub_sub, [])
    )

    class TestHandler(_WebhookHandler):
        cancellation_service = None
        jotform_api_key = ""

    server = HTTPServer(("127.0.0.1", 0), TestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()


class TestWebhookHandlerResponses:
    def test_unknown_path_returns_404_json(self, webhook_server):
        conn = HTTPConnection("127.0.0.1", webhook_server)
        conn.request("POST", "/unknown/path")
        resp = conn.getresponse()
        body = json.loads(resp.read())

        assert resp.status == 404
        assert body["error"] == "Not Found"
        assert body["path"] == "/unknown/path"
        conn.close()

    def test_missing_submission_id_returns_400_json(self, webhook_server):
        conn = HTTPConnection("127.0.0.1", webhook_server)
        payload = urlencode({"rawRequest": "{}"}).encode()
        conn.request(
            "POST",
            "/webhook/cancellation",
            body=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(payload)),
            },
        )
        resp = conn.getresponse()
        body = json.loads(resp.read())

        assert resp.status == 400
        assert body["error"] == "Missing submissionID"
        conn.close()

    def test_valid_submission_returns_200_json(self, webhook_server):
        conn = HTTPConnection("127.0.0.1", webhook_server)
        payload = urlencode({"submissionID": "5001"}).encode()
        conn.request(
            "POST",
            "/webhook/cancellation",
            body=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(payload)),
            },
        )
        resp = conn.getresponse()
        body = json.loads(resp.read())

        assert resp.status == 200
        assert body["status"] == "accepted"
        assert body["submission_id"] == "5001"
        conn.close()
