from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.models import DriveFile, SettlementRow, SurveySubmission


@runtime_checkable
class SpreadsheetGateway(Protocol):
    def save_settlement_row(
        self,
        row: SettlementRow,
        sheet_name: str | None = None,
        *,
        is_update: bool = False,
    ) -> None: ...

    def append_issue_log_row(self, row: SettlementRow, sync_key: str) -> None: ...

    def find_row_by_booking_key(
        self, booking_key: str, sheet_name: str | None = None
    ) -> int | None: ...

    def is_settlement_completed(self, booking_key: str) -> bool: ...

    def get_completed_booking_keys(self) -> set[str]: ...

    def update_settlement_transfer(
        self, booking_key: str, note: str, transfer_status: str
    ) -> None: ...


@runtime_checkable
class SlackMessageReader(Protocol):
    def get_user_name(self, user_id: str) -> str: ...

    def get_thread_url(self, channel_id: str, thread_ts: str) -> str: ...

    def get_parent_message(self, channel_id: str, thread_ts: str) -> str | None: ...

    def find_message_by_text(
        self,
        channel_id: str,
        search_text: str,
        *,
        max_pages: int = 10,
    ) -> str | None: ...

    def list_channel_messages(
        self,
        channel_id: str,
        *,
        oldest: float = 0,
        max_pages: int = 10,
    ) -> Iterator[dict]: ...


@runtime_checkable
class SlackMessageWriter(Protocol):
    def post_message(
        self,
        *,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        thread_ts: str | None = None,
    ) -> str: ...

    def update_message(
        self,
        *,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> None: ...

    def delete_message(self, *, channel: str, ts: str) -> None: ...

    def post_ephemeral(
        self,
        *,
        channel: str,
        user: str,
        text: str,
        thread_ts: str | None = None,
    ) -> None: ...

    def upload_file(
        self,
        *,
        channel: str,
        thread_ts: str,
        content: bytes,
        filename: str,
        title: str = "",
    ) -> None: ...

    def add_reaction(self, *, channel: str, timestamp: str, name: str) -> None: ...


@runtime_checkable
class SurveySheetGateway(Protocol):
    def get_all_submissions(self) -> list[SurveySubmission]: ...
    def mark_processed(self, submission_id: str) -> None: ...
    def write_formatted_row(self, submission: SurveySubmission) -> None: ...


@runtime_checkable
class DriveImageGateway(Protocol):
    def find_folder(self, folder_name: str) -> str | None: ...
    def list_image_files(self, folder_id: str) -> list[DriveFile]: ...
    def download_file(self, file_id: str) -> bytes: ...
