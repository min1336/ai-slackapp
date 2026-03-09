from __future__ import annotations

import json
from email.parser import BytesParser
from email.policy import default as _email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from app.core import get_logger
from app.services.jotform_parser import fetch_jotform_submission, parse_jotform_answers

if TYPE_CHECKING:
    from app.services.cancellation_image_service import CancellationImageService

logger = get_logger(__name__)


def _parse_multipart(content_type: str, body: bytes) -> dict[str, str]:
    """multipart/form-data body를 파싱하여 {name: value} dict를 반환."""
    raw = f"Content-Type: {content_type}\r\n\r\n".encode() + body
    msg = BytesParser(policy=_email_policy).parsebytes(raw)
    fields: dict[str, str] = {}
    if msg.is_multipart():
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if name:
                payload = part.get_content()
                if isinstance(payload, str):
                    fields[name] = payload.strip()
    return fields


def extract_submission_id(body: bytes, content_type: str = "") -> str | None:
    """Jotform POST body에서 submissionID만 추출한다."""
    try:
        if "multipart/form-data" in content_type:
            fields = _parse_multipart(content_type, body)
            return fields.get("submissionID") or None
        parsed = parse_qs(body.decode("utf-8"))
        return parsed["submissionID"][0]
    except (KeyError, IndexError, UnicodeDecodeError):
        return None


class _WebhookHandler(BaseHTTPRequestHandler):
    """Jotform webhook POST 요청을 처리하는 핸들러."""

    cancellation_service: CancellationImageService | None = None
    jotform_api_key: str = ""

    def _send_json_response(self, code: int, body: dict) -> None:
        """JSON 응답을 전송한다."""
        payload = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if urlparse(self.path).path != "/webhook/cancellation":
            logger.warning("webhook_unknown_path", path=self.path, method="POST")
            self._send_json_response(404, {"error": "Not Found", "path": self.path})
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            self._send_json_response(400, {"error": "Invalid Content-Length"})
            return
        body = self.rfile.read(content_length)
        content_type = self.headers.get("Content-Type", "")

        submission_id = extract_submission_id(body, content_type)
        if not submission_id:
            logger.warning(
                "webhook_missing_submission_id",
                path=self.path,
                content_type=content_type,
            )
            self._send_json_response(400, {"error": "Missing submissionID"})
            return

        # 즉시 200 응답 후 비동기 처리 (Jotform 타임아웃 방지)
        self._send_json_response(
            200, {"status": "accepted", "submission_id": submission_id}
        )

        try:
            content = fetch_jotform_submission(self.jotform_api_key, submission_id)
            sub, file_urls = parse_jotform_answers(submission_id, content)
            logger.info(
                "webhook_received",
                submission_id=sub.submission_id,
                booking_key=sub.booking_key,
                file_count=len(file_urls),
            )
            if self.cancellation_service:
                self.cancellation_service.handle_webhook(sub, file_urls)
        except Exception:
            logger.exception("webhook_processing_failed", submission_id=submission_id)

    def log_message(self, format, *args):
        """stdlib 기본 로깅 억제 — structlog 사용."""


def start_webhook_server(
    service: CancellationImageService,
    api_key: str,
    port: int = 8080,
) -> None:
    """Webhook HTTP 서버를 daemon thread로 시작한다."""

    class Handler(_WebhookHandler):
        cancellation_service = service
        jotform_api_key = api_key

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("webhook_server_started", port=port)
