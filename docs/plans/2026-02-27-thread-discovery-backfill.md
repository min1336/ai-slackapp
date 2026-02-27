# Thread Discovery Backfill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 봇 시작 시 예약 채널의 최근 7일 메시지를 백필하여 ThreadReference DB 캐시를 채우고, 이관 메시지 도착 시 원본 스레드를 확실히 찾을 수 있도록 한다.

**Architecture:** `SlackMessageReader` Protocol에 `list_channel_messages` 메서드를 추가하고, `ThreadDiscoveryService`에 `backfill_reservation_threads()` 메서드를 추가한다. 봇 시작 시 `main.py`에서 한 번 호출. 실시간 캐싱 경로(`_cache_reservation_origin_thread`)에 파싱 실패 로깅도 보강한다.

**Tech Stack:** Python 3.12+, Slack SDK (`conversations_history`), SQLAlchemy (ThreadReference), pytest + FakeDatabase/FakeSlackReader

---

### Task 1: FakeSlackReader에 list_channel_messages 추가

**Files:**
- Modify: `tests/fakes/fake_slack.py:8-36`
- Test: `tests/unit/test_thread_discovery_service.py`

**Step 1: FakeSlackReader에 channel_messages 필드와 list_channel_messages 메서드 추가**

`tests/fakes/fake_slack.py`의 `FakeSlackReader`에 추가:

```python
from collections.abc import Iterator

class FakeSlackReader:
    def __init__(self) -> None:
        self.user_names: dict[str, str] = {}
        self.thread_urls: dict[tuple[str, str], str] = {}
        self.parent_messages: dict[tuple[str, str], str | None] = {}
        self.messages_by_text: dict[tuple[str, str], str | None] = {}
        self.channel_messages: dict[str, list[dict]] = {}  # 추가

    # ... 기존 메서드 유지 ...

    def list_channel_messages(
        self,
        channel_id: str,
        *,
        oldest: float = 0,
        max_pages: int = 50,
    ) -> Iterator[dict]:
        for msg in self.channel_messages.get(channel_id, []):
            ts = float(msg.get("ts", "0"))
            if ts < oldest:
                return
            yield msg
```

**Step 2: 테스트 실행하여 기존 테스트가 깨지지 않는지 확인**

Run: `uv run pytest tests/unit/test_thread_discovery_service.py -v`
Expected: 기존 테스트 모두 PASS

**Step 3: 커밋**

```bash
git add tests/fakes/fake_slack.py
git commit -m "TEST: (AI-135) FakeSlackReader에 list_channel_messages 추가"
```

---

### Task 2: Infrastructure 레이어 — list_channel_messages raw 함수

**Files:**
- Modify: `app/infrastructure/slack_client.py` (끝에 추가)
- Modify: `app/infrastructure/protocols.py:35-48`

**Step 1: slack_client.py에 list_channel_messages 함수 추가**

`app/infrastructure/slack_client.py` 끝에 추가:

```python
from collections.abc import Iterator

def list_channel_messages(
    client: WebClient,
    channel_id: str,
    *,
    oldest: float = 0,
    max_pages: int = 50,
    page_size: int = 200,
) -> Iterator[dict]:
    """채널 메시지를 최신→과거 순으로 yield. oldest 이전 메시지에서 중단."""
    cursor = None
    for _ in range(max_pages):
        try:
            kwargs: dict = {
                "channel": channel_id,
                "limit": page_size,
            }
            if oldest:
                kwargs["oldest"] = str(oldest)
            if cursor:
                kwargs["cursor"] = cursor

            result = client.conversations_history(**kwargs)
        except SlackApiError:
            return

        for msg in result.get("messages", []):
            yield msg

        metadata = result.get("response_metadata", {})
        cursor = metadata.get("next_cursor")
        if not cursor:
            break
```

**Step 2: Protocol에 시그니처 추가**

`app/infrastructure/protocols.py`의 `SlackMessageReader` Protocol에 추가:

```python
from collections.abc import Iterator

class SlackMessageReader(Protocol):
    # ... 기존 메서드 유지 ...

    def list_channel_messages(
        self,
        channel_id: str,
        *,
        oldest: float = 0,
        max_pages: int = 50,
    ) -> Iterator[dict]: ...
```

**Step 3: lint 확인**

Run: `uv run ruff check app/infrastructure/slack_client.py app/infrastructure/protocols.py`
Expected: 에러 없음

**Step 4: 커밋**

```bash
git add app/infrastructure/slack_client.py app/infrastructure/protocols.py
git commit -m "FEAT: (AI-135) list_channel_messages raw 함수 및 Protocol 시그니처 추가"
```

---

### Task 3: SlackReader 서비스에 list_channel_messages 위임 메서드

**Files:**
- Modify: `app/services/slack_reader.py`

**Step 1: SlackReader에 위임 메서드 추가**

`app/services/slack_reader.py`에 추가:

```python
from collections.abc import Iterator

from app.infrastructure.slack_client import (
    list_channel_messages as _list_channel_messages,
)

class SlackReader:
    # ... 기존 메서드 유지 ...

    def list_channel_messages(
        self,
        channel_id: str,
        *,
        oldest: float = 0,
        max_pages: int = 50,
    ) -> Iterator[dict]:
        return _list_channel_messages(
            self._client, channel_id, oldest=oldest, max_pages=max_pages
        )
```

**Step 2: lint 확인**

Run: `uv run ruff check app/services/slack_reader.py`
Expected: 에러 없음

**Step 3: 커밋**

```bash
git add app/services/slack_reader.py
git commit -m "FEAT: (AI-135) SlackReader에 list_channel_messages 위임 메서드 추가"
```

---

### Task 4: backfill_reservation_threads 실패 테스트 작성 (Red)

**Files:**
- Modify: `tests/unit/test_thread_discovery_service.py`

**Step 1: 백필 테스트 클래스 추가**

`tests/unit/test_thread_discovery_service.py` 끝에 추가:

```python
import time


class TestBackfillReservationThreads:
    def test_백필로_채널_메시지에서_booking_key를_캐시한다(
        self, fake_db, fake_reader, service
    ):
        now = time.time()
        fake_reader.channel_messages["C_ISSUE"] = [
            {"text": "예약번호 : BK-100\n업체 : 테스트\n예약자명 : 홍길동", "ts": str(now - 100), "channel": "C_ISSUE"},
            {"text": "예약번호 : BK-200\n업체 : 테스트2\n예약자명 : 김철수", "ts": str(now - 200), "channel": "C_ISSUE"},
        ]

        result = service.backfill_reservation_threads(days=7)

        assert result == 2
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            assert repo.get_by_booking_key("BK-100") is not None
            assert repo.get_by_booking_key("BK-200") is not None

    def test_이미_DB에_있는_건은_스킵한다(self, fake_db, fake_reader, service):
        now = time.time()
        # DB에 미리 저장
        service.register_origin_thread(
            booking_key="BK-100", channel_id="C_ISSUE", thread_ts="existing.ts"
        )
        fake_reader.channel_messages["C_ISSUE"] = [
            {"text": "예약번호 : BK-100\n업체 : 테스트\n예약자명 : 홍길동", "ts": str(now - 100), "channel": "C_ISSUE"},
            {"text": "예약번호 : BK-200\n업체 : 테스트2\n예약자명 : 김철수", "ts": str(now - 200), "channel": "C_ISSUE"},
        ]

        result = service.backfill_reservation_threads(days=7)

        assert result == 1  # BK-200만 신규 저장
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("BK-100")
            assert ref.thread_ts == "existing.ts"  # 덮어쓰지 않음

    def test_파싱_안되는_메시지는_스킵한다(self, fake_reader, service):
        now = time.time()
        fake_reader.channel_messages["C_ISSUE"] = [
            {"text": "관련 없는 메시지입니다", "ts": str(now - 100), "channel": "C_ISSUE"},
        ]

        result = service.backfill_reservation_threads(days=7)

        assert result == 0

    def test_채널_미설정시_0_반환(self, store, fake_reader):
        svc = ThreadDiscoveryService(store, fake_reader, reservation_channel="")

        result = svc.backfill_reservation_threads(days=7)

        assert result == 0

    def test_스레드_답글은_스킵한다(self, fake_reader, service):
        now = time.time()
        fake_reader.channel_messages["C_ISSUE"] = [
            {"text": "예약번호 : BK-100\n업체 : 테스트\n예약자명 : 홍길동", "ts": str(now - 100), "channel": "C_ISSUE", "thread_ts": "parent.ts"},
        ]

        result = service.backfill_reservation_threads(days=7)

        assert result == 0
```

**Step 2: 테스트 실행하여 실패 확인**

Run: `uv run pytest tests/unit/test_thread_discovery_service.py::TestBackfillReservationThreads -v`
Expected: FAIL — `AttributeError: 'ThreadDiscoveryService' object has no attribute 'backfill_reservation_threads'`

**Step 3: 커밋 (Red)**

```bash
git add tests/unit/test_thread_discovery_service.py
git commit -m "TEST: (AI-135) backfill_reservation_threads 실패 테스트 추가 (Red)"
```

---

### Task 5: backfill_reservation_threads 구현 (Green)

**Files:**
- Modify: `app/services/thread_discovery_service.py`

**Step 1: backfill_reservation_threads 메서드 구현**

`app/services/thread_discovery_service.py`의 `ThreadDiscoveryService` 클래스에 추가.
import 섹션에 `time` 추가, `from app.services.message_parser import parse_settlement_message` 추가:

```python
import time

from app.services.message_parser import parse_settlement_message

class ThreadDiscoveryService:
    # ... 기존 코드 유지 ...

    def backfill_reservation_threads(self, days: int = 7) -> int:
        """봇 시작 시 예약 채널의 최근 N일 메시지를 DB에 백필한다.

        Returns:
            신규 저장된 ThreadReference 수
        """
        reservation_channel = self._reservation_channel
        if not reservation_channel:
            logger.warning("backfill_skipped_no_channel")
            return 0

        oldest = time.time() - (days * 86400)
        saved = 0

        try:
            for msg in self._reader.list_channel_messages(
                reservation_channel, oldest=oldest
            ):
                if msg.get("thread_ts"):
                    continue

                text = msg.get("text", "")
                if not text:
                    continue

                parsed = parse_settlement_message(text)
                booking_key = parsed.booking_key.strip()
                if not booking_key:
                    continue

                channel_id = msg.get("channel", reservation_channel)
                message_ts = msg.get("ts", "")
                if not message_ts:
                    continue

                existing = self._store.get_by_booking_key(booking_key)
                if existing:
                    continue

                self._store.save(
                    booking_key=booking_key,
                    channel_id=channel_id,
                    thread_ts=message_ts,
                )
                saved += 1
        except Exception:
            logger.exception("backfill_error", saved_so_far=saved)

        logger.info("backfill_completed", saved=saved)
        return saved
```

**Step 2: 테스트 실행하여 통과 확인**

Run: `uv run pytest tests/unit/test_thread_discovery_service.py::TestBackfillReservationThreads -v`
Expected: 5개 테스트 모두 PASS

**Step 3: 전체 테스트 실행**

Run: `uv run pytest tests/unit -v`
Expected: 모두 PASS

**Step 4: 커밋 (Green)**

```bash
git add app/services/thread_discovery_service.py
git commit -m "FEAT: (AI-135) backfill_reservation_threads 구현"
```

---

### Task 6: main.py에 백필 호출 추가

**Files:**
- Modify: `app/main.py:96-105`

**Step 1: 봇 시작 시 backfill 호출 추가**

`app/main.py`의 `main()` 함수에서, DB 설정 확인 블록 안에 백필 호출 추가:

```python
def main():
    # ... 기존 코드 유지 ...
    container = ServiceContainer(bolt_app.client)

    app_config = get_app_config()
    database = get_database_settings()
    if database.is_configured:
        container.sync_service.recover_stale_sync_records()
        container.discovery.backfill_reservation_threads(days=7)  # 추가
        _start_sync_worker(container.sync_service, app_config.sync_schedule)
    else:
        logger.warning(
            "database_not_configured",
            consequence="sync_worker_disabled",
        )
    # ... 나머지 코드 유지 ...
```

`container.discovery.backfill_reservation_threads(days=7)` 한 줄을 `recover_stale_sync_records()` 바로 다음에 추가한다.

**Step 2: lint 확인**

Run: `uv run ruff check app/main.py`
Expected: 에러 없음

**Step 3: 커밋**

```bash
git add app/main.py
git commit -m "FEAT: (AI-135) 봇 시작 시 예약 스레드 백필 호출 추가"
```

---

### Task 7: 실시간 캐싱 보강 — 파싱 실패 로깅

**Files:**
- Modify: `app/listener/messages.py:139-142`

**Step 1: 파싱 실패 시 debug 로그 추가**

`app/listener/messages.py`의 `_cache_reservation_origin_thread` 함수에서:

```python
def _cache_reservation_origin_thread(message: dict, discovery) -> None:
    channel_id = message.get("channel")
    message_ts = message.get("ts")
    text = message.get("text", "")
    # 부모 메시지(원문)만 캐시: 스레드 댓글은 제외
    if not channel_id or not message_ts or not text or message.get("thread_ts"):
        return

    parsed = parse_settlement_message(text)
    booking_key = parsed.booking_key.strip()
    if not booking_key:
        logger.debug(                          # 추가
            "reservation_cache_skip_no_booking_key",
            text_preview=text[:80],
        )
        return

    # ... 나머지 동일 ...
```

`booking_key`가 빈 문자열인 경우 `logger.debug`로 텍스트 미리보기를 남긴다. `text[:80]`으로 80자만 잘라서 로그 크기를 제한한다.

**Step 2: lint 확인**

Run: `uv run ruff check app/listener/messages.py`
Expected: 에러 없음

**Step 3: 전체 테스트**

Run: `uv run pytest tests/unit -v`
Expected: 모두 PASS

**Step 4: 커밋**

```bash
git add app/listener/messages.py
git commit -m "FEAT: (AI-135) 예약 캐싱 파싱 실패 시 debug 로깅 추가"
```

---

### Task 8: 최종 검증

**Step 1: 전체 테스트 + 커버리지**

Run: `uv run pytest tests/unit -v --cov=app --cov-report=term-missing`
Expected: 모두 PASS, 새 코드 커버리지 확인

**Step 2: lint + format**

Run: `uv run ruff check --fix && uv run ruff format`
Expected: 에러 없음

**Step 3: alembic 체크 (DB 변경 없으므로 통과해야 함)**

Run: `uv run alembic check`
Expected: No new upgrade operations detected (ThreadReference 테이블은 이미 존재)
