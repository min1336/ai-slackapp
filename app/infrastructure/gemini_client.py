from __future__ import annotations

import json
import time

from google import genai
from google.genai import types

from app.core import get_logger

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
            contents.append(types.Part.from_bytes(data=img, mime_type="image/png"))
        contents.append(prompt)

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
                error_str = str(e).lower()
                if "rate" in error_str or "quota" in error_str or "429" in error_str:
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
