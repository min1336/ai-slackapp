from __future__ import annotations

from typing import TYPE_CHECKING

from app.core import get_logger

if TYPE_CHECKING:
    from app.infrastructure.protocols import ImageAnalysisGateway

logger = get_logger(__name__)


def is_rate_limit_error(e: Exception) -> bool:
    """429/rate-limit/quota 에러인지 판별한다."""
    msg = str(e).lower()
    return (
        "429" in msg
        or "rate limit" in msg
        or "rate_limit" in msg
        or "ratelimit" in msg
        or "too many requests" in msg
        or "quota" in msg
        or "exhausted" in msg
    )


class FallbackImageGateway:
    """Primary gateway 실패 시 fallback으로 전환. ImageAnalysisGateway 구현."""

    def __init__(
        self,
        primary: ImageAnalysisGateway,
        fallback: ImageAnalysisGateway,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def analyze_images(self, *, images: list[bytes], prompt: str) -> dict:
        try:
            return self._primary.analyze_images(images=images, prompt=prompt)
        except Exception as e:
            if not is_rate_limit_error(e):
                raise
            logger.warning(
                "primary_rate_limited_fallback",
                error=str(e)[:200],
            )
            return self._fallback.analyze_images(images=images, prompt=prompt)
