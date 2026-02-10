# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

Slack 스레드에서 정산 이슈를 등록하고 승인/반려 워크플로우를 처리하는 봇. Socket Mode를 사용하며 Google Sheets에 데이터를 저장한다.

## 주요 명령어

```bash
# 의존성 설치
uv sync

# 앱 실행
uv run python -m app.main

# 테스트
uv run pytest tests/unit -v                                # 유닛 테스트
uv run pytest tests/unit -v --cov=app --cov-report=term-missing  # 커버리지 포함

# 린팅
uv run ruff check --fix            # 자동 수정
uv run ruff format                 # 포매팅

# 커밋 전 검증 (pre-commit이 ruff + ruff-format + pytest-unit 자동 실행)
uv run ruff check && uv run pytest tests/unit -q

# Pre-commit 설정
uv run pre-commit install
```

## 아키텍처

레이어드 아키텍처를 따르며, **레이어를 건너뛰어 호출하지 않는다**:

```
listener/ (Controller)     ← Slack 이벤트 수신, services/views 호출
    ├── payload.py         ← Slack body 파싱 헬퍼 (TypedDict, MessageContext)
    ↓
services/                  ← 비즈니스 로직, infrastructure 호출
    ↓
infrastructure/            ← 외부 시스템 통신 (Slack API, Google Sheets)
    ├── protocols.py       ← Protocol 인터페이스 (DI용)
    ↓
models/                    ← 모든 레이어에서 import 가능
views/                     ← Slack Block Kit JSON 생성 (데이터 가공 금지)
core/                      ← 공통 유틸 (logger.py: structlog 설정)
```

**경계 규칙:**
- `listener/` → `infrastructure/` 직접 호출 금지
- `services/` → `listener/` 호출 금지
- `views/`는 순수하게 Block Kit JSON만 생성

**DI 패턴:** `infrastructure/protocols.py`에 Protocol 인터페이스 정의. 서비스는 Protocol 타입으로 의존성을 받고, 기본값은 실제 구현체. 테스트에서 Fake 주입 (`tests/fakes/`).

## 설정 구조

- `.env`: Slack 토큰, Google 자격 증명, DB 연결 정보 (Pydantic Settings로 로드)
- `config.yaml`: 승인자 목록, 스프레드시트 ID, 채널 ID

## 데이터베이스

Supabase (PostgreSQL)를 캐시 레이어로 사용. Google Sheets가 primary storage.

**동기화 방향:**
- DB → Sheets: `save_settlement()` → `after_commit` → `sync_to_sheets()` (활성)
- Sheets → DB: `_lazy_sync_settlement_completed()` — Sheets 정산완료를 DB에 반영 (구현됨, 미활성. `save_settlement()`에서 `repo.save()` 전에 호출하여 활성화)

```bash
# 마이그레이션 상태 확인
uv run alembic current

# 자동 마이그레이션 생성 (모델 변경 감지)
uv run alembic revision --autogenerate -m "설명"

# 마이그레이션 적용
uv run alembic upgrade head

# 모델-DB 드리프트 확인
uv run alembic check
```

**Alembic 설정:** `env.py`에서 `app.config.database.url`을 읽어 DB 연결. `alembic.ini`에 ruff post-write 훅 설정.
**모델-DB 호환:** `_BigIntPK = BigInteger().with_variant(Integer, "sqlite")` — PostgreSQL bigint + SQLite autoincrement 호환. 부분 인덱스는 `postgresql_where` + `sqlite_where` 병행.
**새 부분 인덱스 추가 시:** `postgresql_where`만 쓰면 SQLite 테스트가 깨짐. 반드시 `sqlite_where` 동시 지정 (boolean: PG `false` → SQLite `0`).

## 데이터 모델

| 용도 | 모델 타입 |
|------|-----------|
| JSON 직렬화/검증 필요 (Slack 버튼 value 등) | Pydantic `BaseModel` |
| 단순 데이터 홀더 (스프레드시트 행 등) | `@dataclass` |

예: `SettlementData`(Pydantic)는 버튼 value로 전달, `SettlementRow`(dataclass)는 시트 행 변환용.

**금액 필드:** `int | None` (모델 내부), Slack UI 경계에서만 `str` 변환. `parse_cost` validator가 `"1,000,000원"` → `1000000` 자동 변환.

**새 필드 추가 시 체크리스트:**
1. `models/settlement.py` - Pydantic/dataclass 필드
2. `models/__init__.py` - 새 모델 export 추가 (누락 시 런타임 ImportError)
3. `infrastructure/database/repository.py` - `_SHARED_FIELDS` 튜플에 추가 (save/add_log 자동 반영)
4. `infrastructure/database/models.py` - SQLAlchemy 컬럼 (DB 저장 필요시)
5. `uv run alembic revision --autogenerate -m "설명"` - 마이그레이션 생성 후 확인
6. `config.yaml` `spreadsheet.columns` - 시트 컬럼 매핑 추가 (시트 표시 필요시)

## 핵심 흐름

1. **정산 이슈**: 스레드에서 `!정산` 명령 → 원본 메시지 파싱 → 모달 → 승인 요청 → 시트 저장
2. **이관 예약**: 이관 채널 메시지 자동 감지 → 파싱 → 예약 채널의 기존 정산이슈 스레드 탐색(DB→Slack API 폴백) → 해당 스레드에 포스트 → 이관 후 예약번호 체인 저장

## 로깅 (structlog)

- `from app.core import get_logger` → `logger = get_logger(__name__)`
- 이벤트명: 영어 snake_case (예: `settlement_approve_failed`, `sync_completed`)
- 컨텍스트: 키워드 인자 (`logger.info("event", booking_key=key, error=str(e))`)
- `logger.exception()` 자동으로 traceback 포함 — `exc_info=True` 불필요
- 환경별 출력: dev=컬러 콘솔(`ConsoleRenderer`), prod=JSON(`JSONRenderer`)
- **주의:** `structlog.stdlib.add_logger_name`은 `PrintLoggerFactory`와 호환 불가

## 에러 핸들링 패턴

### 패턴 선택 가이드

**1. 예상된 비즈니스 에러 → 명시적 try/except**
```python
try:
    save_settlement(data, status, approver_name)
except AlreadyProcessedError:
    logger.info("already_processed", booking_key=key)
    notify_user_safe(client, user_id, "이미 처리된 건입니다.")
    return
except ValidationError:
    logger.exception("validation_failed", booking_key=key)
    notify_user_safe(client, user_id, "입력값이 올바르지 않습니다.")
    return
```

**언제**:
- 비즈니스 로직에서 예상되는 에러 (AlreadyProcessedError, ValidationError)
- 에러 타입별로 다른 처리가 필요한 경우
- 사용자에게 다른 메시지를 보여줘야 하는 경우

**2. Best-effort cleanup → contextlib.suppress (구체적 타입)**
```python
from contextlib import suppress

# ✅ GOOD - 구체적인 에러 타입
with suppress(SlackApiError):
    client.chat_delete(channel=channel_id, ts=message_ts)

# ❌ BAD - 너무 광범위
with suppress(Exception):  # KeyError, AttributeError까지 숨김!
    client.chat_delete(channel=channel_id, ts=message_ts)
```

**언제**:
- Cleanup 작업 (메시지 삭제, 임시 데이터 정리)
- 실패해도 주 작업에 영향 없는 부가 작업
- **반드시 구체적인 예외 타입 사용** (SlackApiError, SQLAlchemyError, APIError 등)

**3. 사용자 알림 → 공통 유틸리티**
```python
from app.listener.error_utils import notify_user_safe

# 알림 실패를 신경 쓰지 않아도 됨
notify_user_safe(client, user_id, "⚠️ 오류 메시지")
```

**언제**:
- 사용자에게 에러 알림을 보낼 때
- 알림 실패가 주 작업 실패로 이어지지 않아야 할 때

### suppress 사용 체크리스트

- [ ] 구체적인 예외 타입을 사용했는가? (Exception 사용 금지)
- [ ] 이 작업이 실패해도 주 작업에 영향이 없는가?
- [ ] 실패 시 로깅이 이미 되어 있는가? (suppress 내부에서는 로깅 불가)
- [ ] 명시적 try/except가 의도를 더 명확히 하지 않는가?

### 금지 패턴

```python
# ❌ 절대 사용 금지
with suppress(Exception):  # 모든 에러를 숨김
    important_business_logic()

# ❌ 금지 - 로깅 없이 무시
with suppress(SlackApiError):
    critical_operation()  # 실패를 어디서도 알 수 없음

# ✅ 대신 이렇게
try:
    critical_operation()
except SlackApiError:
    logger.exception("critical_operation_failed")
    # 필요시 재시도, 대체 로직, 사용자 알림 등
```

### 예외 계층

**기본 구조** (`app/exceptions.py`): `AppError(message, user_message, details)` → `SpreadsheetError` | `SlackError` | `ValidationError`.

**서브클래스 규칙**: `_default_user_message` 클래스 변수로 기본 메시지 정의 (MRO 기반). `user_message`는 사용자에게 표시, `details`는 모니터링 알림에 포함.

**글로벌 핸들러**: `error_handler.py`에서 사용자/시스템 에러 분류, 모니터링 알림 전송. Slack Bolt의 `@app.error` 핸들러가 주입하는 `logger` 파라미터는 `**_kwargs`로 무시 (모듈 레벨 structlog 사용).

## 테스트

- `tests/factories.py`의 `SettlementDataFactory.create(**overrides)` 사용하여 테스트 데이터 생성
- `tests/fakes/` — Protocol 기반 Fake 구현체 (외부 의존성 없이 테스트)
- `tests/fakes/fake_database.py` — 인메모리 SQLite `FakeDatabase`. Repository 테스트 시 `fake_db.get_session`을 `session_factory`로 주입
- `FakeSpreadsheet.completed_keys: set[str]` — 정산완료 시뮬레이션용 (`find_row_by_booking_key`가 None 반환)
- `tests/conftest.py` — 공유 픽스처 (팩토리 기반)
- Pre-commit 훅: ruff + ruff-format + pytest-unit (3개 모두 커밋 시 자동 실행)

## 코드 스타일

- `from __future__ import annotations` 필수 (ruff isort 설정)
- Python 3.12+, line-length 88
- 선택된 ruff 규칙: E, W, F, I, UP, B, SIM, C4, FA
- 상수(`ActionId`, `BlockId`): `StrEnum` 사용, `app/constants/slack_ids.py`에 정의

**Pythonic 관용구:**
- dataclass는 순수 데이터 홀더 — `__post_init__` 사이드이펙트 금지, 생성 로직은 `@classmethod` 팩토리에
- 반복 필드 매핑은 튜플/dict 상수로 DRY 처리 (예: `repository.py`의 `_SHARED_FIELDS`)
- Slack body 파싱 등 외부 데이터 접근 시 EAFP(try/except) 선호 — LBYL(isinstance 체크) 대신
- `TYPE_CHECKING` import는 OK, 함수 내부 inline import는 circular dependency 있을 때만 허용

## Slack Block Kit 주의사항

- `say()`는 현재 채널에만 포스트 — 다른 채널에 포스트하려면 `client.chat_postMessage()` 사용
- `header` 블록은 `plain_text`만 지원 → mrkdwn 문법(`~취소선~`, `*볼드*`) 사용 불가
- mrkdwn 필요시 `section` 블록 사용: `{"type": "section", "text": {"type": "mrkdwn", "text": "~취소선~"}}`

## gspread 주의사항

- gspread 6.x에서 `CellNotFound` 예외가 공개 API에서 제거됨 — `from gspread.exceptions import CellNotFound` 불가
- `_is_cell_not_found()`가 `__class__.__name__` 문자열 비교를 사용하는 것은 의도적 (isinstance 변환 금지)

## CI/CD

**CI (`ci.yml`):** 모든 PR에서 2개 job 병렬 실행:
- `lint`: `ruff check` + `ruff format --check`
- `test`: `pytest tests/unit -v`

**Migration Check (`ci-migration.yml`):** PR → main 시에만 실행:
- `alembic`: fresh SQLite에서 `alembic heads` (단일 head 확인) → `upgrade head` → `check`

**배포 (`deploy.yml`):** main push 시 Docker 빌드 → 프로덕션 배포. `entrypoint.sh`가 `alembic upgrade head` 실행 후 앱 시작.

**`ALEMBIC_DATABASE_URL`:** 이 환경변수가 설정되면 `.env` 기반 PG URL 대신 사용. CI에서 `sqlite:///test.db`로 설정하여 PG 없이 마이그레이션 검증.

## 커밋 컨벤션

- 형식: `TYPE: (TICKET) 설명` (예: `FEAT: (AI-98) 시트 동기화 추가`)
- TYPE: `FEAT`, `FIX`, `TEST`, `DOCS`, `CHORE`, `REFACTOR`
- TICKET: 현재 브랜치명에서 추출 (예: `feat/AI-100` → `AI-100`)
- 기능 단위로 커밋, 필요시 squash
- **커밋 전 `uv run ruff format` 먼저 실행** — pre-commit의 ruff-format 훅이 stash 충돌을 일으킬 수 있음
