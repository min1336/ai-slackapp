from __future__ import annotations

import base64
import json

from openai import OpenAI

from app.core import get_logger

logger = get_logger(__name__)


def _detect_mime(data: bytes) -> str:
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


class OpenAIImageClient:
    """GPT-4o-mini Vision API 래퍼. ImageAnalysisGateway Protocol 구현."""

    def __init__(self, *, api_key: str, model: str, timeout: int) -> None:
        self._client = OpenAI(api_key=api_key, timeout=timeout)
        self._model = model
        self._timeout = timeout

    def analyze_images(self, *, images: list[bytes], prompt: str) -> dict:
        content: list[dict] = []
        for img in images:
            b64 = base64.b64encode(img).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{_detect_mime(img)};base64,{b64}",
                        "detail": "high",
                    },
                }
            )
        content.append({"type": "text", "text": prompt})

        logger.info(
            "openai_request_started",
            model=self._model,
            image_count=len(images),
            prompt_length=len(prompt),
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        raw_text = response.choices[0].message.content or ""
        logger.debug(
            "openai_raw_text",
            text_length=len(raw_text),
            text_preview=raw_text[:500],
        )
        return json.loads(raw_text)
