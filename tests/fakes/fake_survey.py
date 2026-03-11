from __future__ import annotations

from app.models import SurveySubmission


class FakeSurveySheet:
    """SurveySheetGateway Protocol 호환 Fake."""

    def __init__(self) -> None:
        self.submissions: list[SurveySubmission] = []
        self.processed_ids: list[str] = []
        self.formatted_rows: list[SurveySubmission] = []

    def get_all_submissions(self) -> list[SurveySubmission]:
        return self.submissions

    def mark_processed(self, submission_id: str) -> None:
        self.processed_ids.append(submission_id)

    def write_formatted_row(self, submission: SurveySubmission) -> None:
        self.formatted_rows.append(submission)
