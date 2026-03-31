from __future__ import annotations

from app.models.cancellation import DriveFile


class FakeDrive:
    """DriveImageGateway Protocol 호환 Fake."""

    def __init__(self):
        self.folders: dict[str, str] = {}
        self.files: dict[str, list[DriveFile]] = {}
        self.file_contents: dict[str, bytes] = {}

    def find_folder(self, folder_name: str) -> str | None:
        # contains 매칭 + 최신 우선 (프로덕션 Drive API와 동일 동작)
        matches = [name for name in self.folders if folder_name in name]
        if not matches:
            return None
        # 폴더명에 날짜가 포함되므로 역순 정렬 = 최신
        matches.sort(reverse=True)
        return self.folders[matches[0]]

    def list_image_files(self, folder_id: str) -> list[DriveFile]:
        return self.files.get(folder_id, [])

    def download_file(self, file_id: str) -> bytes:
        return self.file_contents[file_id]
