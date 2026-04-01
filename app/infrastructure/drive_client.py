from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.core import get_logger
from app.models import DriveFile

logger = get_logger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class DriveImageClient:
    """Google Drive에서 이미지 폴더를 검색하고 파일을 다운로드한다."""

    def __init__(
        self,
        credentials_file: str,
        parent_folder_id: str,
    ) -> None:
        self._parent_folder_id = parent_folder_id
        credentials = Credentials.from_service_account_file(
            credentials_file, scopes=DRIVE_SCOPES
        )
        self._service: Any = build("drive", "v3", credentials=credentials)

    def find_folder(self, folder_name: str) -> str | None:
        safe_name = folder_name.replace("\\", "\\\\").replace("'", "\\'")
        query = (
            f"name contains '{safe_name}' "
            f"and '{self._parent_folder_id}' in parents "
            f"and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        results = (
            self._service.files()
            .list(
                q=query,
                fields="files(id, name)",
                orderBy="createdTime desc",
                pageSize=100,
            )
            .execute()
        )
        # 부분일치 오매칭 방지: booking_key가 독립 토큰으로 존재해야 함
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(folder_name)}(?![A-Za-z0-9])"
        )
        for f in results.get("files", []):
            if pattern.search(f["name"]):
                logger.info(
                    "drive_folder_found",
                    folder_name=folder_name,
                    folder_id=f["id"],
                )
                return f["id"]
        logger.debug("drive_folder_not_found", folder_name=folder_name)
        return None

    def list_image_files(self, folder_id: str) -> list[DriveFile]:
        query = (
            f"'{folder_id}' in parents"
            f" and (mimeType contains 'image/' or mimeType='application/pdf')"
            f" and trashed=false"
        )
        results = (
            self._service.files()
            .list(q=query, fields="files(id, name, mimeType)", pageSize=100)
            .execute()
        )
        files = [
            DriveFile(id=f["id"], name=f["name"], mime_type=f["mimeType"])
            for f in results.get("files", [])
        ]
        logger.info("drive_images_listed", folder_id=folder_id, count=len(files))
        return files

    def download_file(self, file_id: str) -> bytes:
        request = self._service.files().get_media(fileId=file_id)
        buffer = BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()
