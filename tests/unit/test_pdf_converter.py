from __future__ import annotations

import pymupdf

from app.services.pdf_converter import PdfConverter


def _make_pdf_bytes(pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=100, height=100)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestPdfConverter:
    def test_단일_페이지_변환(self):
        converter = PdfConverter()
        result = converter.convert(_make_pdf_bytes(1), "cert.pdf")

        assert len(result) == 1
        name, data = result[0]
        assert name == "cert.png"
        assert data[:4] == b"\x89PNG"

    def test_다페이지_변환_파일명_규칙(self):
        converter = PdfConverter()
        result = converter.convert(_make_pdf_bytes(3), "multi.pdf")

        assert len(result) == 3
        names = [name for name, _ in result]
        assert names == ["multi_p1.png", "multi_p2.png", "multi_p3.png"]
        for _, data in result:
            assert data[:4] == b"\x89PNG"

    def test_경로_포함_파일명에서_stem_추출(self):
        converter = PdfConverter()
        result = converter.convert(_make_pdf_bytes(1), "folder/sub/doc.pdf")

        assert result[0][0] == "doc.png"
