from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from app.core import get_logger

if TYPE_CHECKING:
    from app.infrastructure.protocols import DriveImageGateway
    from app.models.cancellation import DriveFile
    from app.services.pdf_converter import PdfConverter

logger = get_logger(__name__)


class CollectedFiles(NamedTuple):
    """수집된 파일 목록과 PDF 포함 여부."""

    images: list[tuple[str, bytes]]
    has_pdf: bool


class DriveFileCollector:
    """Drive에서 파일을 다운로드하고 PDF를 이미지로 변환하는 컴포넌트."""

    def __init__(
        self,
        drive: DriveImageGateway,
        pdf_converter: PdfConverter,
    ) -> None:
        self._drive = drive
        self._pdf_converter = pdf_converter

    def collect(self, folder_name: str) -> CollectedFiles | None:
        """폴더 찾기 → 파일 목록 → 다운로드 + PDF 변환.

        폴더/파일이 없거나 모든 다운로드가 실패하면 None을 반환한다.
        """
        folder_id = self._drive.find_folder(folder_name)
        if not folder_id:
            logger.info("drive_collect_no_folder", folder_name=folder_name)
            return None

        files = self._drive.list_image_files(folder_id)
        if not files:
            logger.info("drive_collect_no_files", folder_name=folder_name)
            return None

        logger.debug(
            "drive_collect_files_found",
            folder_name=folder_name,
            file_count=len(files),
            file_names=[f.name for f in files],
        )

        return self._download_files(files)

    def _download_files(self, files: list[DriveFile]) -> CollectedFiles | None:
        downloads: list[tuple[str, bytes]] = []
        has_pdf = False
        for file in files:
            try:
                content = self._drive.download_file(file.id)
                if file.mime_type == "application/pdf":
                    images = self._pdf_converter.convert(content, file.name)
                    logger.info(
                        "drive_collect_pdf_converted",
                        file_name=file.name,
                        pages=len(images),
                    )
                    downloads.extend(images)
                    has_pdf = True
                else:
                    downloads.append((file.name, content))
            except Exception:
                logger.exception(
                    "drive_collect_download_failed",
                    file_name=file.name,
                )

        if not downloads:
            return None
        return CollectedFiles(images=downloads, has_pdf=has_pdf)
