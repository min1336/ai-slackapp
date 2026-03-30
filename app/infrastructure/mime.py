from __future__ import annotations


def detect_mime(data: bytes) -> str:
    """Magic bytes 기반 이미지 MIME 타입 감지."""
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"
