from __future__ import annotations

from app.models import SurveySubmission

_Q_CUSTOMER_NAME = "12"
_Q_BOOKING_KEY = "14"
_Q_COMPANY_NAME = "26"
_Q_PHONE = "13"
_Q_FILE_UPLOAD = "11"
_Q_NOTE = "17"


def parse_jotform_webhook(
    submission_id: str,
    raw_request: dict,
) -> tuple[SurveySubmission, list[str]]:
    """Jotform webhook rawRequest에서 SurveySubmission + 파일 URL을 추출한다."""

    def _text(qid: str) -> str:
        answer = raw_request.get(qid, {}).get("answer", "")
        if isinstance(answer, dict):
            return str(answer.get("full", ""))
        return str(answer)

    file_answer = raw_request.get(_Q_FILE_UPLOAD, {}).get("answer", [])
    file_urls = list(file_answer) if isinstance(file_answer, list) else []

    submission = SurveySubmission(
        submission_id=submission_id,
        customer_name=_text(_Q_CUSTOMER_NAME),
        booking_key=_text(_Q_BOOKING_KEY),
        company_name=_text(_Q_COMPANY_NAME),
        phone=_text(_Q_PHONE),
        note=_text(_Q_NOTE),
    )

    return submission, file_urls
