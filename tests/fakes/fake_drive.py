from __future__ import annotations

from app.models.cancellation import DriveFile


class FakeDrive:
    """DriveImageGateway Protocol 호환 Fake."""

    def __init__(self):
        self.folders: dict[str, str] = {}
        self.files: dict[str, list[DriveFile]] = {}
        self.file_contents: dict[str, bytes] = {}

    def find_folder(self, folder_name: str) -> str | None:
        return self.folders.get(folder_name)

    def list_image_files(self, folder_id: str) -> list[DriveFile]:
        return self.files.get(folder_id, [])

    def download_file(self, file_id: str) -> bytes:
        return self.file_contents[file_id]
