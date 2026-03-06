from __future__ import annotations

from app.models import SurveySubmission


class FakeSurveySheet:
    """SurveySheetGateway Protocol 호환 Fake."""

    def __init__(self) -> None:
        self.formatted_rows: list[SurveySubmission] = []

    def write_formatted_row(self, submission: SurveySubmission) -> None:
        self.formatted_rows.append(submission)
