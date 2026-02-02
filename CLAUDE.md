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

# Pre-commit 설정
uv run pre-commit install
```

## 아키텍처

레이어드 아키텍처를 따르며, **레이어를 건너뛰어 호출하지 않는다**:

```
listener/ (Controller)     ← Slack 이벤트 수신, services/views 호출
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

## 핵심 흐름

1. **정산 이슈**: 스레드에서 `!정산` 명령 → 원본 메시지 파싱 → 모달 → 승인 요청 → 시트 저장
2. **이관 예약**: 특정 채널에 메시지 작성 시 자동 감지 → 파싱 → 모달 → 승인/반려

## 코드 스타일

- `from __future__ import annotations` 필수 (ruff isort 설정)
- Python 3.12+, line-length 88
- 선택된 ruff 규칙: E, W, F, I, UP, B, SIM, C4, FA
