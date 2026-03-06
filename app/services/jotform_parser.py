from __future__ import annotations

import json
import urllib.request

from app.core import get_logger
from app.models import SurveySubmission

logger = get_logger(__name__)

_JOTFORM_API_BASE = "https://api.jotform.com"

_Q_CUSTOMER_NAME = "12"
_Q_BOOKING_KEY = "14"
_Q_COMPANY_NAME = "26"
_Q_PHONE = "13"
_Q_FILE_UPLOAD = "11"
_Q_NOTE = "17"


def fetch_jotform_submission(api_key: str, submission_id: str) -> dict:
    """Jotform API에서 submission content를 조회한다."""
    url = f"{_JOTFORM_API_BASE}/submission/{submission_id}?apiKey={api_key}"
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        data = json.loads(resp.read())
    return data["content"]


def parse_jotform_answers(
    submission_id: str,
    content: dict,
) -> tuple[SurveySubmission, list[str]]:
    """Jotform API content에서 SurveySubmission + 파일 URL을 추출한다."""
    answers = content.get("answers", {})

    def _text(qid: str) -> str:
        answer = answers.get(qid, {}).get("answer", "")
        if isinstance(answer, dict):
            return str(answer.get("full", ""))
        return str(answer)

    file_answer = answers.get(_Q_FILE_UPLOAD, {}).get("answer", [])
    file_urls = list(file_answer) if isinstance(file_answer, list) else []

    created_at = content.get("created_at", "")

    submission = SurveySubmission(
        submission_id=submission_id,
        customer_name=_text(_Q_CUSTOMER_NAME),
        booking_key=_text(_Q_BOOKING_KEY),
        company_name=_text(_Q_COMPANY_NAME),
        phone=_text(_Q_PHONE),
        note=_text(_Q_NOTE),
        submission_date=created_at,
    )

    return submission, file_urls
