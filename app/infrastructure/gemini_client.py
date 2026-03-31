from __future__ import annotations

import json
import time

from google import genai
from google.genai import types

from app.core import get_logger
from app.infrastructure.fallback_gateway import is_rate_limit_error
from app.infrastructure.mime import detect_mime

logger = get_logger(__name__)

_MAX_RETRIES = 1
_RETRY_BACKOFF = 2.0  # seconds


class GeminiClient:
    """Gemini Flash API 래퍼. ImageAnalysisGateway Protocol 구현."""

    def __init__(self, *, api_key: str, model: str, timeout: int) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._timeout = timeout

    def analyze_images(self, *, images: list[bytes], prompt: str) -> dict:
        contents: list[types.Part | str] = []
        for img in images:
            mime = detect_mime(img)
            contents.append(types.Part.from_bytes(data=img, mime_type=mime))
        contents.append(prompt)

        logger.info(
            "gemini_request_started",
            model=self._model,
            image_count=len(images),
            prompt_length=len(prompt),
        )
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        http_options=types.HttpOptions(timeout=self._timeout * 1000),
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                logger.debug(
                    "gemini_raw_text",
                    text_length=len(response.text) if response.text else 0,
                    text_preview=(response.text or "")[:500],
                )
                if not response.text:
                    raise ValueError(
                        "Gemini returned empty response (possible safety filter)"
                    )
                return json.loads(response.text)
            except (TimeoutError, ConnectionError) as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "gemini_retry",
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    time.sleep(_RETRY_BACKOFF * (attempt + 1))
            except Exception as e:
                if is_rate_limit_error(e):
                    last_error = e
                    if attempt < _MAX_RETRIES:
                        logger.warning(
                            "gemini_rate_limit_retry",
                            attempt=attempt + 1,
                            error=str(e),
                        )
                        time.sleep(_RETRY_BACKOFF * (attempt + 1))
                        continue
                raise

        raise last_error  # type: ignore[misc]
