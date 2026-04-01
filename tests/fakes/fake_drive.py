from __future__ import annotations

import re

from app.models.cancellation import DriveFile


class _OrderedDict(dict):
    """삽입 순서를 별도 리스트로 추적하는 dict (createdTime desc 시뮬레이션용)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.insert_order: list[str] = []

    def __setitem__(self, key, value):
        if key not in self:
            self.insert_order.append(key)
        super().__setitem__(key, value)


class FakeDrive:
    """DriveImageGateway Protocol 호환 Fake."""

    def __init__(self):
        self.folders: _OrderedDict = _OrderedDict()
        self.files: dict[str, list[DriveFile]] = {}
        self.file_contents: dict[str, bytes] = {}

    def find_folder(self, folder_name: str) -> str | None:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(folder_name)}(?![A-Za-z0-9])"
        )
        # 최근 삽입 순(= prod의 createdTime desc)으로 순회
        for name in reversed(self.folders.insert_order):
            if name in self.folders and pattern.search(name):
                return self.folders[name]
        return None

    def list_image_files(self, folder_id: str) -> list[DriveFile]:
        return self.files.get(folder_id, [])

    def download_file(self, file_id: str) -> bytes:
        return self.file_contents[file_id]
