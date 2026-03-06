# Jotform Webhook 기반 결항 처리 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 5분 폴링(Google Sheets + Drive)을 Jotform webhook 기반 즉시 처리로 전환한다.

**Architecture:** Jotform이 폼 제출 시 HTTP POST를 보내면, 봇 내부 HTTP 서버가 수신하여 파일을 Jotform URL에서 직접 다운로드하고 Slack에 업로드한다. Socket Mode는 유지하고, 별도 daemon thread에서 HTTP 서버를 실행한다.

**Tech Stack:** Python stdlib (`http.server`, `urllib.request`), 새 의존성 없음

---

### Task 1: Jotform Webhook 페이로드 파서

**Files:**
- Create: `app/services/jotform_parser.py`
- Test: `tests/unit/test_jotform_parser.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_jotform_parser.py
from __future__ import annotations

from app.services.jotform_parser import parse_jotform_webhook


class TestParseJotformWebhook:
    def test_정상_페이로드_파싱(self):
        raw_request = {
            "12": {"answer": "홍길동"},
            "14": {"answer": "R12345"},
            "26": {"answer": "렌트카A"},
            "13": {"answer": {"full": "010-1234-5678"}},
            "11": {"answer": [
                "https://jotform.com/uploads/file.pdf",
                "https://jotform.com/uploads/image.png",
            ]},
            "17": {"answer": "추가 메모"},
        }
        sub, file_urls = parse_jotform_webhook(
            submission_id="99001",
            raw_request=raw_request,
        )

        assert sub.submission_id == "99001"
        assert sub.customer_name == "홍길동"
        assert sub.booking_key == "R12345"
        assert sub.company_name == "렌트카A"
        assert sub.phone == "010-1234-5678"
        assert sub.note == "추가 메모"
        assert file_urls == [
            "https://jotform.com/uploads/file.pdf",
            "https://jotform.com/uploads/image.png",
        ]

    def test_선택_필드_비어있어도_파싱(self):
        raw_request = {
            "12": {"answer": "김철수"},
            "14": {"answer": "WB999"},
            "26": {"answer": ""},
            "13": {"answer": {"full": ""}},
            "11": {"answer": ["https://jotform.com/uploads/a.jpg"]},
        }
        sub, file_urls = parse_jotform_webhook(
            submission_id="99002",
            raw_request=raw_request,
        )

        assert sub.customer_name == "김철수"
        assert sub.booking_key == "WB999"
        assert sub.company_name == ""
        assert sub.phone == ""
        assert sub.note == ""
        assert len(file_urls) == 1

    def test_파일_없으면_빈_리스트(self):
        raw_request = {
            "12": {"answer": "테스트"},
            "14": {"answer": "AB111"},
            "26": {"answer": ""},
            "13": {"answer": {"full": ""}},
            "11": {},
        }
        _, file_urls = parse_jotform_webhook(
            submission_id="99003",
            raw_request=raw_request,
        )
        assert file_urls == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_jotform_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# app/services/jotform_parser.py
from __future__ import annotations

from app.models import SurveySubmission

# Jotform Question ID → 필드 매핑
_Q_CUSTOMER_NAME = "12"
_Q_BOOKING_KEY = "14"
_Q_COMPANY_NAME = "26"
_Q_PHONE = "13"
_Q_FILE_UPLOAD = "11"
_Q_NOTE = "17"


def parse_jotform_webhook(
    submission_id: str,
    raw_request: dict,
) -> tuple[SurveySubmission, list[str]]:
    """Jotform webhook rawRequest에서 SurveySubmission + 파일 URL을 추출한다."""

    def _text(qid: str) -> str:
        answer = raw_request.get(qid, {}).get("answer", "")
        if isinstance(answer, dict):
            return str(answer.get("full", ""))
        return str(answer)

    file_answer = raw_request.get(_Q_FILE_UPLOAD, {}).get("answer", [])
    file_urls = list(file_answer) if isinstance(file_answer, list) else []

    submission = SurveySubmission(
        submission_id=submission_id,
        customer_name=_text(_Q_CUSTOMER_NAME),
        booking_key=_text(_Q_BOOKING_KEY),
        company_name=_text(_Q_COMPANY_NAME),
        phone=_text(_Q_PHONE),
        note=_text(_Q_NOTE),
    )

    return submission, file_urls
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_jotform_parser.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/jotform_parser.py tests/unit/test_jotform_parser.py
git commit -m "FEAT: Jotform webhook 페이로드 파서 추가"
```

---

### Task 2: CancellationImageService 리팩토링 — webhook 기반

**Files:**
- Modify: `app/services/cancellation_image_service.py`
- Modify: `tests/unit/test_cancellation_image_service.py`
- Modify: `tests/fakes/fake_survey.py`
- Modify: `app/infrastructure/protocols.py`

**핵심 변경:**
- `poll_and_upload()` 제거
- `handle_webhook(sub, file_urls)` 신규 메서드 추가
- `DriveImageGateway` 의존성 제거
- `SurveySheetGateway`에서 `get_all_submissions`, `mark_processed` 제거
- 파일 다운로드를 URL 기반 콜백으로 변경

**Step 1: SurveySheetGateway 축소**

`app/infrastructure/protocols.py` — `SurveySheetGateway`에서 폴링 메서드 제거:

```python
@runtime_checkable
class SurveySheetGateway(Protocol):
    def write_formatted_row(self, submission: SurveySubmission) -> None: ...
```

**Step 2: FakeSurveySheet 축소**

`tests/fakes/fake_survey.py`:

```python
from __future__ import annotations
from app.models import SurveySubmission


class FakeSurveySheet:
    """SurveySheetGateway Protocol 호환 Fake."""

    def __init__(self) -> None:
        self.formatted_rows: list[SurveySubmission] = []

    def write_formatted_row(self, submission: SurveySubmission) -> None:
        self.formatted_rows.append(submission)
```

**Step 3: Write failing tests for new handle_webhook**

`tests/unit/test_cancellation_image_service.py` — 기존 TestPollAndUpload/TestSheetBasedTracking 교체:

```python
class TestHandleWebhook:
    def test_파일_URL에서_다운로드_후_업로드(self):
        sub = _submission()
        survey = FakeSurveySheet()

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, writer=writer, reader=reader)
        svc.handle_webhook(sub, file_urls=["https://example.com/img.jpg"])

        assert len(writer.uploaded_files) == 1
        assert writer.uploaded_files[0]["filename"] == "img.jpg"

    def test_스레드_없으면_업로드_안함(self):
        sub = _submission()
        survey = FakeSurveySheet()
        writer = FakeSlackWriter()

        svc = _make_service(survey=survey, writer=writer)
        svc.handle_webhook(sub, file_urls=["https://example.com/img.jpg"])

        assert len(writer.uploaded_files) == 0
        assert len(survey.formatted_rows) == 0

    def test_성공_시_운영현황_시트_작성(self):
        sub = _submission()
        survey = FakeSurveySheet()

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        svc = _make_service(survey=survey, reader=reader)
        svc.handle_webhook(sub, file_urls=["https://example.com/a.jpg"])

        assert len(survey.formatted_rows) == 1

    def test_빈_파일_URL이면_업로드_안함(self):
        sub = _submission()
        survey = FakeSurveySheet()
        writer = FakeSlackWriter()

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        svc = _make_service(survey=survey, writer=writer, reader=reader)
        svc.handle_webhook(sub, file_urls=[])

        assert len(writer.uploaded_files) == 0
```

**Step 4: Refactor CancellationImageService**

```python
# app/services/cancellation_image_service.py
class CancellationImageService:
    def __init__(
        self,
        survey_sheet: SurveySheetGateway,
        writer: SlackMessageWriter,
        reader: SlackMessageReader,
        target_channel: str,
        file_downloader: Callable[[str], bytes] = _default_download,
    ) -> None:
        self._survey_sheet = survey_sheet
        self._writer = writer
        self._reader = reader
        self._target_channel = target_channel
        self._download = file_downloader

    def handle_webhook(
        self, sub: SurveySubmission, file_urls: list[str]
    ) -> bool:
        """Jotform webhook에서 받은 파일 URL을 Slack 스레드에 업로드한다."""
        thread_ts = self._reader.find_message_by_text(
            self._target_channel, sub.booking_key
        )
        if not thread_ts:
            logger.info("cancellation_no_thread", booking_key=sub.booking_key)
            return False

        if not file_urls:
            logger.info("cancellation_no_files", booking_key=sub.booking_key)
            return False

        uploaded, has_pdf = self._upload_files(file_urls, thread_ts, sub.booking_key)

        if uploaded == 0:
            return False

        if has_pdf:
            with suppress(SlackApiError):
                self._writer.add_reaction(
                    channel=self._target_channel, timestamp=thread_ts, name=_PDF_EMOJI,
                )

        self._survey_sheet.write_formatted_row(sub)
        logger.info("cancellation_uploaded", booking_key=sub.booking_key, count=uploaded)
        return True
```

파일 다운로드 기본 구현 (stdlib):

```python
import urllib.request

def _default_download(url: str) -> bytes:
    with urllib.request.urlopen(url) as resp:
        return resp.read()
```

**Step 5: _make_service 헬퍼 업데이트 (테스트)**

```python
def _make_service(
    *,
    survey: FakeSurveySheet | None = None,
    writer: FakeSlackWriter | None = None,
    reader: FakeSlackReader | None = None,
) -> CancellationImageService:
    return CancellationImageService(
        survey_sheet=survey or FakeSurveySheet(),
        writer=writer or FakeSlackWriter(),
        reader=reader or FakeSlackReader(),
        target_channel=TARGET_CH,
        file_downloader=lambda url: b"\xff\xd8",  # stub downloader
    )
```

**Step 6: Run tests**

Run: `uv run pytest tests/unit/test_cancellation_image_service.py -v`
Expected: PASS (기존 PDF 테스트도 file_downloader stub으로 전환)

**Step 7: Commit**

```bash
git add app/services/cancellation_image_service.py app/infrastructure/protocols.py \
       tests/unit/test_cancellation_image_service.py tests/fakes/fake_survey.py
git commit -m "REFACTOR: CancellationImageService를 webhook 기반으로 전환"
```

---

### Task 3: Webhook HTTP 서버

**Files:**
- Create: `app/listener/webhook.py`
- Test: `tests/unit/test_webhook_server.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_webhook_server.py
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import Mock
from urllib.parse import urlencode

from app.listener.webhook import parse_jotform_post_body


class TestParseJotformPostBody:
    def test_urlencoded_rawRequest_파싱(self):
        raw = json.dumps({
            "12": {"answer": "홍길동"},
            "14": {"answer": "R12345"},
            "26": {"answer": "업체A"},
            "13": {"answer": {"full": "010-0000-0000"}},
            "11": {"answer": ["https://jotform.com/file.jpg"]},
        })
        body = urlencode({"submissionID": "5001", "rawRequest": raw}).encode()
        result = parse_jotform_post_body(body)

        assert result is not None
        sub, file_urls = result
        assert sub.submission_id == "5001"
        assert sub.booking_key == "R12345"
        assert file_urls == ["https://jotform.com/file.jpg"]

    def test_잘못된_body_None_반환(self):
        result = parse_jotform_post_body(b"garbage data")
        assert result is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_webhook_server.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# app/listener/webhook.py
from __future__ import annotations

import json
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from app.core import get_logger
from app.services.jotform_parser import parse_jotform_webhook

if TYPE_CHECKING:
    from app.models import SurveySubmission
    from app.services.cancellation_image_service import CancellationImageService

logger = get_logger(__name__)


def parse_jotform_post_body(
    body: bytes,
) -> tuple[SurveySubmission, list[str]] | None:
    """Jotform POST body(urlencoded)를 파싱하여 SurveySubmission + file_urls를 반환."""
    try:
        parsed = parse_qs(body.decode("utf-8"))
        submission_id = parsed["submissionID"][0]
        raw_request = json.loads(parsed["rawRequest"][0])
    except (KeyError, IndexError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    return parse_jotform_webhook(submission_id, raw_request)


class WebhookHandler(BaseHTTPRequestHandler):
    cancellation_service: CancellationImageService | None = None

    def do_POST(self):
        if self.path != "/webhook/cancellation":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        result = parse_jotform_post_body(body)
        if result is None:
            logger.warning("webhook_invalid_payload")
            self.send_response(400)
            self.end_headers()
            return

        sub, file_urls = result
        logger.info(
            "webhook_received",
            submission_id=sub.submission_id,
            booking_key=sub.booking_key,
            file_count=len(file_urls),
        )

        if self.cancellation_service:
            self.cancellation_service.handle_webhook(sub, file_urls)

        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # stdlib 로깅 대신 structlog 사용
        pass


def start_webhook_server(
    service: CancellationImageService,
    port: int = 8080,
) -> None:
    """Webhook HTTP 서버를 daemon thread로 시작한다."""
    handler = partial(WebhookHandler)
    handler.cancellation_service = service  # type: ignore[attr-defined]

    server = HTTPServer(("0.0.0.0", port), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("webhook_server_started", port=port)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_webhook_server.py tests/unit/test_jotform_parser.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/listener/webhook.py tests/unit/test_webhook_server.py
git commit -m "FEAT: Jotform webhook HTTP 서버 구현"
```

---

### Task 4: Container + Main 와이어링

**Files:**
- Modify: `app/container.py`
- Modify: `app/main.py`
- Modify: `app/config.py`

**Step 1: Config 변경**

`app/config.py` — `CancellationConfig`에서 Drive/poll 제거, webhook 추가:

```python
class CancellationConfig(BaseModel):
    slack_channels: CancellationSlackChannelsConfig = CancellationSlackChannelsConfig()
    spreadsheet: CancellationSpreadsheetConfig = CancellationSpreadsheetConfig()
    webhook_port: int = 8080
```

`CancellationDriveConfig` 클래스, `poll_schedule` 필드 제거.

**Step 2: Container 변경**

`app/container.py` — Drive/SurveySheetReader 폴링 제거, webhook 와이어링:

```python
# 제거: DriveImageClient, SurveySheetReader (get_all/mark_processed)
# SurveySheetReader는 write_formatted_row만 사용 → 유지

cancel_cfg = config.cancellation
cancel_target = cancel_cfg.slack_channels.target
cancel_sheet_id = cancel_cfg.spreadsheet.id

if cancel_target and cancel_sheet_id:
    def _create_cancel_spreadsheet() -> gspread.Spreadsheet:
        credentials = Credentials.from_service_account_file(
            spreadsheet_settings.credentials_file, scopes=SCOPES,
        )
        gc = gspread.authorize(credentials)
        return gc.open_by_key(cancel_sheet_id)

    _survey = SurveySheetReader(
        client_factory=_create_cancel_spreadsheet,
        sheet_name=cancel_cfg.spreadsheet.survey_sheet_name,
        formatted_sheet_name=cancel_cfg.spreadsheet.formatted_sheet_name,
    )
    self.cancellation_image = CancellationImageService(
        survey_sheet=_survey,
        writer=self.writer,
        reader=self.reader,
        target_channel=cancel_target,
    )
else:
    self.cancellation_image = None

self.cancellation_webhook_port = cancel_cfg.webhook_port
```

**Step 3: Main 변경**

`app/main.py` — 폴링 워커 제거, webhook 서버 추가:

```python
# 제거: _start_cancellation_worker(), 관련 import

# 추가:
from app.listener.webhook import start_webhook_server

# main() 내:
if container.cancellation_image:
    start_webhook_server(
        container.cancellation_image,
        port=container.cancellation_webhook_port,
    )
else:
    logger.info("cancellation_webhook_disabled")
```

**Step 4: config YAML 업데이트**

`config.dev.yaml`, `config.prod.yaml`, `config.test.yaml`:

```yaml
cancellation:
  slack_channels:
    target: "C0AANUJGPAB"
  spreadsheet:
    id: "..."
    survey_sheet_name: "..."
    formatted_sheet_name: "운영현황"
  webhook_port: 8080
  # drive, poll_schedule 제거
```

**Step 5: Run all tests**

Run: `uv run pytest tests/unit -v`
Expected: PASS

**Step 6: Commit**

```bash
git add app/container.py app/main.py app/config.py \
       config.dev.yaml config.prod.yaml config.test.yaml
git commit -m "FEAT: webhook 서버 와이어링, 폴링 워커 제거"
```

---

### Task 5: Docker 설정 업데이트

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `docker-compose.local.yml`

**Step 1: docker-compose.prod.yml 포트 추가**

```yaml
services:
  slack-bot:
    # ... 기존 설정 유지 ...
    ports:
      - "8080:8080"
```

**Step 2: docker-compose.local.yml 포트 추가**

```yaml
services:
  slack-bot:
    # ... 기존 설정 유지 ...
    ports:
      - "8080:8080"
```

**Step 3: Commit**

```bash
git add docker-compose.prod.yml docker-compose.local.yml
git commit -m "CHORE: webhook 포트 8080 노출"
```

---

### Task 6: 레거시 코드 제거

**Files:**
- Delete: `app/infrastructure/drive_client.py`
- Delete: `tests/unit/test_drive_client.py`
- Delete: `tests/fakes/fake_drive.py`
- Modify: `app/infrastructure/survey_sheet.py` — `get_all_submissions`, `mark_processed` 제거
- Modify: `tests/unit/test_survey_sheet_reader.py` — 관련 테스트 제거
- Modify: `app/infrastructure/protocols.py` — `DriveImageGateway` 제거
- Modify: `app/models/__init__.py` — `DriveFile` export 확인
- Modify: `app/models/cancellation.py` — `DriveFile` 제거 (더 이상 사용 안 함)

**Step 1: Drive 관련 파일 삭제**

```bash
git rm app/infrastructure/drive_client.py
git rm tests/unit/test_drive_client.py
git rm tests/fakes/fake_drive.py
```

**Step 2: DriveImageGateway 프로토콜 제거**

`app/infrastructure/protocols.py`에서 `DriveImageGateway` 클래스 삭제.
`DriveFile` import도 제거.

**Step 3: DriveFile 모델 제거**

`app/models/cancellation.py`에서 `DriveFile` dataclass 삭제.
`app/models/__init__.py`에서 `DriveFile` export 제거.

**Step 4: SurveySheetReader 축소**

`app/infrastructure/survey_sheet.py`에서 제거:
- `get_all_submissions()` 메서드
- `mark_processed()` 메서드
- `_PROCESSED_COL` 상수
- `_get_row_value()` 헬퍼 (write_formatted_row에서 사용 안 하면)

유지: `write_formatted_row()`, `__init__()`, `_get_client()`

**Step 5: Run all tests**

Run: `uv run pytest tests/unit -v`
Expected: PASS

**Step 6: Commit**

```bash
git add -A
git commit -m "REFACTOR: Drive/폴링 레거시 코드 제거"
```

---

### Task 7: 최종 검증

**Step 1: Lint**

Run: `uv run ruff check --fix && uv run ruff format`

**Step 2: Full test**

Run: `uv run pytest tests/unit -v --cov=app --cov-report=term-missing`

**Step 3: 로컬 실행 테스트**

```bash
# 터미널 1: 앱 시작
uv run python -m app.main

# 터미널 2: webhook 테스트
curl -X POST http://localhost:8080/webhook/cancellation \
  -d "submissionID=test001&rawRequest=$(python3 -c 'import json; print(json.dumps({"12":{"answer":"테스트"},"14":{"answer":"WB000"},"26":{"answer":"업체"},"13":{"answer":{"full":"010-0000-0000"}},"11":{"answer":["https://httpbin.org/image/png"]}}))')"
```

Expected: 로그에 `webhook_received` 출력

**Step 4: Commit**

```bash
git add -A
git commit -m "CHORE: lint 및 최종 정리"
```
