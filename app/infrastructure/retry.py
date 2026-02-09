"""Google Sheets API rate-limit 방어: retry 데코레이터 + TTL 캐시."""

from __future__ import annotations

import functools
import random
import time
from collections.abc import Callable
from threading import Lock
from typing import Any, TypeVar

from gspread.exceptions import APIError

from app.core import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry_on_rate_limit(
    *,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Callable[[F], F]:
    """429 APIError 전용 exponential backoff with full jitter 데코레이터.

    - gspread APIError 중 HTTP 429만 재시도, 그 외는 즉시 전파
    - APIError가 아닌 예외도 즉시 전파
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except APIError as e:
                    if e.response.status_code != 429:
                        raise
                    if attempt >= max_retries:
                        logger.error(
                            "rate_limit_retries_exhausted",
                            function=func.__name__,
                            max_retries=max_retries,
                        )
                        raise
                    ceiling = min(max_delay, base_delay * (2**attempt))
                    delay = random.uniform(0, ceiling)  # noqa: S311
                    logger.warning(
                        "rate_limit_retry",
                        function=func.__name__,
                        attempt=attempt + 1,
                        delay=round(delay, 2),
                    )
                    sleep_fn(delay)

        return wrapper  # type: ignore[return-value]

    return decorator


class TTLCache[K, V]:
    """Thread-safe TTL 캐시.

    Args:
        ttl: 캐시 항목의 유효 시간(초).
        clock: 현재 시간을 반환하는 함수 (테스트용 주입 가능).
    """

    def __init__(
        self,
        ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl
        self._clock = clock
        self._store: dict[K, tuple[float, V]] = {}
        self._lock = Lock()

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if self._clock() >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._store[key] = (self._clock() + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
