"""retry_on_rate_limit 데코레이터 + TTLCache 테스트"""

from __future__ import annotations

import pytest
from gspread.exceptions import APIError
from requests import Response

from app.infrastructure.retry import TTLCache, retry_on_rate_limit


def _make_api_error(status_code: int) -> APIError:
    """지정된 HTTP 상태 코드의 gspread APIError를 생성."""
    import json

    resp = Response()
    resp.status_code = status_code
    resp.headers["Content-Type"] = "application/json"
    resp._content = json.dumps(
        {"error": {"code": status_code, "message": "test", "status": "ERROR"}}
    ).encode()
    return APIError(resp)


# ── retry_on_rate_limit 테스트 ──────────────────────────────


class TestRetryOnRateLimit:
    def test_success_no_retry(self):
        """성공 시 재시도 없이 1회만 호출된다."""
        call_count = 0

        @retry_on_rate_limit(sleep_fn=lambda _: None)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeed() == "ok"
        assert call_count == 1

    def test_429_then_success(self):
        """429 후 재시도하여 성공한다."""
        call_count = 0

        @retry_on_rate_limit(max_retries=3, sleep_fn=lambda _: None)
        def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _make_api_error(429)
            return "recovered"

        assert fail_once() == "recovered"
        assert call_count == 2

    def test_max_retries_exceeded(self):
        """최대 재시도 초과 시 APIError가 전파된다."""

        @retry_on_rate_limit(max_retries=2, sleep_fn=lambda _: None)
        def always_429():
            raise _make_api_error(429)

        with pytest.raises(APIError) as exc_info:
            always_429()
        assert exc_info.value.response.status_code == 429

    def test_non_429_api_error_not_retried(self):
        """429가 아닌 APIError는 재시도하지 않는다."""
        call_count = 0

        @retry_on_rate_limit(max_retries=3, sleep_fn=lambda _: None)
        def fail_403():
            nonlocal call_count
            call_count += 1
            raise _make_api_error(403)

        with pytest.raises(APIError) as exc_info:
            fail_403()
        assert exc_info.value.response.status_code == 403
        assert call_count == 1

    def test_non_api_error_not_retried(self):
        """APIError가 아닌 예외는 재시도하지 않는다."""
        call_count = 0

        @retry_on_rate_limit(max_retries=3, sleep_fn=lambda _: None)
        def fail_value():
            nonlocal call_count
            call_count += 1
            raise ValueError("not an api error")

        with pytest.raises(ValueError, match="not an api error"):
            fail_value()
        assert call_count == 1

    def test_sleep_fn_called_with_valid_delay(self):
        """sleep_fn이 올바른 범위의 delay로 호출된다."""
        delays: list[float] = []
        call_count = 0

        @retry_on_rate_limit(
            max_retries=3,
            base_delay=2.0,
            max_delay=30.0,
            sleep_fn=delays.append,
        )
        def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise _make_api_error(429)
            return "ok"

        assert fail_twice() == "ok"
        assert len(delays) == 2

        # attempt 0: delay ∈ [0, min(30, 2 × 2^0)] = [0, 2]
        assert 0 <= delays[0] <= 2.0
        # attempt 1: delay ∈ [0, min(30, 2 × 2^1)] = [0, 4]
        assert 0 <= delays[1] <= 4.0


# ── TTLCache 테스트 ─────────────────────────────────────────


class TestTTLCache:
    def test_get_set(self):
        """기본 get/set 동작."""
        cache: TTLCache[str, int] = TTLCache(ttl=60.0)
        assert cache.get("a") is None
        cache.set("a", 42)
        assert cache.get("a") == 42

    def test_ttl_expiry(self):
        """TTL 만료 후 None을 반환한다."""
        current_time = 0.0

        def clock() -> float:
            return current_time

        cache: TTLCache[str, str] = TTLCache(ttl=10.0, clock=clock)
        cache.set("key", "value")
        assert cache.get("key") == "value"

        # TTL 직전 — 아직 유효
        current_time = 9.9
        assert cache.get("key") == "value"

        # TTL 만료
        current_time = 10.0
        assert cache.get("key") is None

    def test_clear(self):
        """clear() 후 모든 항목이 제거된다."""
        cache: TTLCache[str, int] = TTLCache(ttl=60.0)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_overwrite(self):
        """같은 키로 set하면 값이 교체된다."""
        cache: TTLCache[str, int] = TTLCache(ttl=60.0)
        cache.set("a", 1)
        cache.set("a", 2)
        assert cache.get("a") == 2

    def test_overwrite_resets_ttl(self):
        """같은 키로 set하면 TTL이 리셋된다."""
        current_time = 0.0

        def clock() -> float:
            return current_time

        cache: TTLCache[str, str] = TTLCache(ttl=10.0, clock=clock)
        cache.set("key", "v1")

        current_time = 8.0
        cache.set("key", "v2")  # TTL 리셋

        current_time = 15.0  # 원래 TTL(10.0)은 만료, 리셋 후(18.0)는 유효
        assert cache.get("key") == "v2"
