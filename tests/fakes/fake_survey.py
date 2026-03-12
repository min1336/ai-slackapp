from __future__ import annotations

from app.models import AnalysisResult, SurveySubmission


class FakeSurveySheet:
    """SurveySheetGateway Protocol 호환 Fake."""

    def __init__(self) -> None:
        self.submissions: list[SurveySubmission] = []
        self.processed_ids: list[str] = []
        self.formatted_rows: list[SurveySubmission] = []
        self.analysis_results: list[tuple[str, AnalysisResult]] = []

    def get_all_submissions(self) -> list[SurveySubmission]:
        return self.submissions

    def mark_processed(self, submission_id: str) -> None:
        self.processed_ids.append(submission_id)

    def write_formatted_row(self, submission: SurveySubmission) -> bool:
        for existing in self.formatted_rows:
            if (
                existing.booking_key == submission.booking_key
                and existing.customer_name == submission.customer_name
            ):
                return False
        self.formatted_rows.append(submission)
        return True

    def write_analysis_result(self, submission_id: str, result: AnalysisResult) -> None:
        self.analysis_results.append((submission_id, result))
