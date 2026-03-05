from __future__ import annotations

from app.models import DriveFile


class FakeDriveClient:
    """DriveImageGateway Protocol 호환 Fake."""

    def __init__(self) -> None:
        self.folders: dict[str, str] = {}  # folder_name → folder_id
        self.files: dict[str, list[DriveFile]] = {}  # folder_id → files
        self.file_contents: dict[str, bytes] = {}  # file_id → bytes

    def find_folder(self, folder_name: str) -> str | None:
        return self.folders.get(folder_name)

    def list_image_files(self, folder_id: str) -> list[DriveFile]:
        return list(self.files.get(folder_id, []))

    def download_file(self, file_id: str) -> bytes:
        return self.file_contents.get(file_id, b"")
