from __future__ import annotations

from pathlib import PurePosixPath

import pymupdf


class PdfConverter:
    """PDF를 페이지별 PNG 이미지로 변환하는 컴포넌트."""

    def convert(self, pdf_bytes: bytes, original_name: str) -> list[tuple[str, bytes]]:
        stem = PurePosixPath(original_name).stem
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        try:
            pages = len(doc)
            result = []
            for i, page in enumerate(doc, 1):
                pix = page.get_pixmap(dpi=150)
                img_name = f"{stem}_p{i}.png" if pages > 1 else f"{stem}.png"
                result.append((img_name, pix.tobytes("png")))
            return result
        finally:
            doc.close()
