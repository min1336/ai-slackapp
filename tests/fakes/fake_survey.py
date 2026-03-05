from __future__ import annotations

from app.models import SurveySubmission


class FakeSurveySheet:
    """SurveySheetGateway Protocol 호환 Fake."""

    def __init__(self, submissions: list[SurveySubmission] | None = None) -> None:
        self.submissions = list(submissions or [])
        self.processed_ids: set[str] = set()
        self.formatted_rows: list[SurveySubmission] = []

    def get_all_submissions(self) -> list[SurveySubmission]:
        return [
            s for s in self.submissions if s.submission_id not in self.processed_ids
        ]

    def mark_processed(self, submission_id: str) -> None:
        self.processed_ids.add(submission_id)

    def write_formatted_row(self, submission: SurveySubmission) -> None:
        self.formatted_rows.append(submission)
