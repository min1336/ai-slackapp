from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from app.core import get_logger
from app.services.jotform_parser import parse_jotform_webhook

if TYPE_CHECKING:
    from app.models import SurveySubmission
    from app.services.cancellation_image_service import CancellationImageService

logger = get_logger(__name__)


def parse_jotform_post_body(
    body: bytes,
) -> tuple[SurveySubmission, list[str]] | None:
    """Jotform POST body(urlencoded)를 파싱하여 SurveySubmission + file_urls를 반환."""
    try:
        parsed = parse_qs(body.decode("utf-8"))
        submission_id = parsed["submissionID"][0]
        raw_request = json.loads(parsed["rawRequest"][0])
    except (KeyError, IndexError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    return parse_jotform_webhook(submission_id, raw_request)


class _WebhookHandler(BaseHTTPRequestHandler):
    """Jotform webhook POST 요청을 처리하는 핸들러."""

    cancellation_service: CancellationImageService | None = None

    def do_POST(self):
        if self.path != "/webhook/cancellation":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        result = parse_jotform_post_body(body)
        if result is None:
            logger.warning("webhook_invalid_payload")
            self.send_response(400)
            self.end_headers()
            return

        sub, file_urls = result
        logger.info(
            "webhook_received",
            submission_id=sub.submission_id,
            booking_key=sub.booking_key,
            file_count=len(file_urls),
        )

        if self.cancellation_service:
            self.cancellation_service.handle_webhook(sub, file_urls)

        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        """stdlib 기본 로깅 억제 — structlog 사용."""


def start_webhook_server(
    service: CancellationImageService,
    port: int = 8080,
) -> None:
    """Webhook HTTP 서버를 daemon thread로 시작한다."""

    class Handler(_WebhookHandler):
        cancellation_service = service

    server = HTTPServer(("0.0.0.0", port), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("webhook_server_started", port=port)
