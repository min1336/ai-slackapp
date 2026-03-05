from __future__ import annotations

from app.models import DriveFile
from tests.fakes.fake_drive import FakeDriveClient


class TestFakeDriveClient:
    """FakeDriveClient이 DriveImageGateway 프로토콜을 올바르게 구현하는지 검증."""

    def test_폴더_검색_성공(self):
        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-id-1"

        assert drive.find_folder("홍길동_R12345") == "folder-id-1"

    def test_폴더_검색_실패시_None(self):
        drive = FakeDriveClient()
        assert drive.find_folder("존재하지않는폴더") is None

    def test_이미지_파일_목록(self):
        drive = FakeDriveClient()
        files = [
            DriveFile(id="f1", name="img1.jpg", mime_type="image/jpeg"),
            DriveFile(id="f2", name="img2.png", mime_type="image/png"),
        ]
        drive.files["folder-id-1"] = files

        result = drive.list_image_files("folder-id-1")
        assert len(result) == 2
        assert result[0].name == "img1.jpg"

    def test_빈_폴더_빈_리스트(self):
        drive = FakeDriveClient()
        assert drive.list_image_files("no-such-folder") == []

    def test_파일_다운로드(self):
        drive = FakeDriveClient()
        drive.file_contents["f1"] = b"\xff\xd8\xff\xe0"

        assert drive.download_file("f1") == b"\xff\xd8\xff\xe0"

    def test_없는_파일_빈_바이트(self):
        drive = FakeDriveClient()
        assert drive.download_file("no-such-file") == b""
