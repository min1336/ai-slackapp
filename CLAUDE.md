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
pytest tests -v                    # 전체 테스트
pytest tests/unit -v               # 유닛 테스트만
pytest tests/integration -v        # 통합 테스트 (실제 구글시트에 기록됨)

# 린팅
uv run ruff check --fix            # 자동 수정
uv run ruff format                 # 포매팅

# 커밋 전 검증 (린트 + 테스트)
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
    ↓
models/                    ← 모든 레이어에서 import 가능
views/                     ← Slack Block Kit JSON 생성 (데이터 가공 금지)
```

**경계 규칙:**
- `listener/` → `infrastructure/` 직접 호출 금지
- `services/` → `listener/` 호출 금지
- `views/`는 순수하게 Block Kit JSON만 생성

## 설정 구조

- `.env`: Slack 토큰, Google 자격 증명, DB 연결 정보 (Pydantic Settings로 로드)
- `config.yaml`: 승인자 목록, 스프레드시트 ID, 채널 ID

## 데이터베이스

Supabase (PostgreSQL)를 캐시 레이어로 사용. Google Sheets가 primary storage.

```bash
# 마이그레이션 적용 (Supabase MCP 플러그인 사용)
# migrations/ 폴더의 SQL 파일을 Supabase apply_migration으로 실행

# 또는 직접 실행
psql -d <database_name> -f migrations/001_add_sync_status.sql
```

**Alembic 미사용**: Supabase 마이그레이션 시스템으로 충분. 별도 설정 불필요.

## 데이터 모델 선택

| 용도 | 모델 타입 |
|------|-----------|
| JSON 직렬화/검증 필요 (Slack 버튼 value 등) | Pydantic `BaseModel` |
| 단순 데이터 홀더 (스프레드시트 행 등) | `@dataclass` |

예: `SettlementData`(Pydantic)는 버튼 value로 전달, `SettlementRow`(dataclass)는 시트 행 변환용.

**새 필드 추가 시 체크리스트:**
1. `models/settlement.py` - Pydantic/dataclass 필드
2. `models/__init__.py` - 새 모델 export 추가 (누락 시 런타임 ImportError)
3. `infrastructure/database/repository.py` - INSERT/UPDATE 쿼리
4. `migrations/` - DB 마이그레이션 SQL
5. `infrastructure/database/models.py` - SQLAlchemy 컬럼 (DB 저장 필요시)

## 핵심 흐름

1. **정산 이슈**: 스레드에서 `!정산` 명령 → 원본 메시지 파싱 → 모달 → 승인 요청 → 시트 저장
2. **이관 예약**: 특정 채널에 메시지 작성 시 자동 감지 → 파싱 → 모달 → 승인/반려

## 에러 핸들링 패턴

`listener/` 핸들러에서 Slack API 호출 시 표준 예외 처리:
```python
try:
    # 핸들러 로직
except (SlackApiError, ValidationError, KeyError):
    logger.exception("처리 중 에러 발생")
```

## 코드 스타일

- `from __future__ import annotations` 필수 (ruff isort 설정)
- Python 3.12+, line-length 88
- 선택된 ruff 규칙: E, W, F, I, UP, B, SIM, C4, FA

## Slack Block Kit 주의사항

- `header` 블록은 `plain_text`만 지원 → mrkdwn 문법(`~취소선~`, `*볼드*`) 사용 불가
- mrkdwn 필요시 `section` 블록 사용: `{"type": "section", "text": {"type": "mrkdwn", "text": "~취소선~"}}`

## 커밋 컨벤션

- 형식: `TYPE: (TICKET) 설명` (예: `FEAT: (AI-98) 시트 동기화 추가`)
- TYPE: `FEAT`, `FIX`, `TEST`, `DOCS`, `CHORE`, `REFACTOR`
- TICKET: 현재 브랜치명에서 추출 (예: `feat/AI-100` → `AI-100`)
- 기능 단위로 커밋, 필요시 squash
