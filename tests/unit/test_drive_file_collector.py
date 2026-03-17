from __future__ import annotations

import pymupdf

from app.models.cancellation import DriveFile
from app.services.drive_file_collector import DriveFileCollector
from app.services.pdf_converter import PdfConverter


class FakeDrive:
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


def _make_pdf_bytes(pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=100, height=100)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _collector(drive: FakeDrive | None = None) -> DriveFileCollector:
    return DriveFileCollector(
        drive=drive or FakeDrive(),
        pdf_converter=PdfConverter(),
    )


class TestCollect:
    def test_폴더_없으면_None(self):
        drive = FakeDrive()
        result = _collector(drive).collect("nonexistent")
        assert result is None

    def test_파일_없으면_None(self):
        drive = FakeDrive()
        drive.folders["folder"] = "id-1"
        drive.files["id-1"] = []
        result = _collector(drive).collect("folder")
        assert result is None

    def test_이미지_파일_수집(self):
        drive = FakeDrive()
        drive.folders["folder"] = "id-1"
        drive.files["id-1"] = [
            DriveFile(id="f1", name="a.jpg", mime_type="image/jpeg"),
            DriveFile(id="f2", name="b.png", mime_type="image/png"),
        ]
        drive.file_contents["f1"] = b"\xff\xd8"
        drive.file_contents["f2"] = b"\x89PNG"

        result = _collector(drive).collect("folder")

        assert result is not None
        assert len(result.images) == 2
        assert result.has_pdf is False

    def test_pdf_변환_후_수집(self):
        drive = FakeDrive()
        drive.folders["folder"] = "id-1"
        drive.files["id-1"] = [
            DriveFile(id="f1", name="doc.pdf", mime_type="application/pdf"),
        ]
        drive.file_contents["f1"] = _make_pdf_bytes(2)

        result = _collector(drive).collect("folder")

        assert result is not None
        assert len(result.images) == 2
        assert result.has_pdf is True
        names = [name for name, _ in result.images]
        assert names == ["doc_p1.png", "doc_p2.png"]

    def test_다운로드_실패_건너뛰기(self):
        drive = FakeDrive()
        drive.folders["folder"] = "id-1"
        drive.files["id-1"] = [
            DriveFile(id="f1", name="bad.jpg", mime_type="image/jpeg"),
            DriveFile(id="f2", name="ok.jpg", mime_type="image/jpeg"),
        ]
        # f1 has no content → KeyError on download
        drive.file_contents["f2"] = b"\xff\xd8"

        result = _collector(drive).collect("folder")

        assert result is not None
        assert len(result.images) == 1
        assert result.images[0][0] == "ok.jpg"

    def test_모든_다운로드_실패_시_None(self):
        drive = FakeDrive()
        drive.folders["folder"] = "id-1"
        drive.files["id-1"] = [
            DriveFile(id="f1", name="bad.jpg", mime_type="image/jpeg"),
        ]
        # no contents → all downloads fail

        result = _collector(drive).collect("folder")
        assert result is None

    def test_이미지_pdf_혼합(self):
        drive = FakeDrive()
        drive.folders["folder"] = "id-1"
        drive.files["id-1"] = [
            DriveFile(id="f1", name="photo.jpg", mime_type="image/jpeg"),
            DriveFile(id="f2", name="cert.pdf", mime_type="application/pdf"),
        ]
        drive.file_contents["f1"] = b"\xff\xd8"
        drive.file_contents["f2"] = _make_pdf_bytes(1)

        result = _collector(drive).collect("folder")

        assert result is not None
        assert result.has_pdf is True
        assert len(result.images) == 2
        names = [name for name, _ in result.images]
        assert "photo.jpg" in names
        assert "cert.png" in names
