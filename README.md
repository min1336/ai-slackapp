# Slack 정산 이슈 봇

Slack 스레드에서 정산 이슈를 등록/승인하고, 결항확인서를 AI로 검증하는 봇.

---

# Part 1. 정산

### 정산 이슈 등록 및 승인

```
사용자가 예약 채널 스레드에서 `!정산` 입력
→ 원본 메시지 자동 파싱 → 모달에서 수정/확인
→ 승인 채널에 승인 요청 포스트
→ 승인자가 승인/반려 → Google Sheets에 기록
```

### 이관 예약 자동 연결

```
업체이관 채널에 메시지 도착
→ 예약번호 파싱 → 해당 예약의 기존 정산이슈 스레드 탐색 (DB → Slack API 폴백)
→ 해당 스레드에 이관 정보 포스트
```

### 데이터 동기화

- **실시간**: DB 저장 → `after_commit` 훅 → Sheets 즉시 반영
- **배치**: 매일 08:00 DB → Sheets 미동기화 건 처리
- **역동기화**: 매일 Sheets `정산완료=TRUE` → DB 반영

---

# Part 2. 결항

### 결항확인서 AI 검증

```
설문 시트(Google Sheets) 폴링 → Google Drive에서 이미지 다운로드
→ Gemini Flash(primary) / GPT-4o-mini(fallback)로 문서 분석
→ 예약 데이터와 교차검증 (승인/반려/보류 판정)
→ 결과를 Slack 채널에 포스팅 + 시트에 기록
```

**활성화 조건** (두 가지 모두 필요):
1. `config.{env}.yaml`의 `cancellation.analysis.enabled: true`
2. `.env`에 `GEMINI_API_KEY` 또는 `OPENAI_API_KEY` 설정

### 해외(일본) 결항 건 처리

예약번호 접두사로 해외 건을 판별하여, AI 분석을 스킵하고 담당팀에 알림만 전달한다.

```
예약번호 prefix 매칭 (OT, HG, KL, IM)
→ AI 분석/교차검증 스킵
→ 스레드에 @해외사업팀_일본파트 멘션 + 🇯🇵 리액션
```

설정: `config.{env}.yaml`의 `cancellation.overseas`

```yaml
overseas:
  prefixes: ["OT", "HG", "KL", "IM"]   # 해외 예약번호 접두사
  mention: "<!subteam^S03KUCG1H53>"     # 해외사업팀_일본파트
  reaction: "flag-jp"                    # 🇯🇵
```

### 외부 서비스 계정

| 서비스 | 계정 | 비고 |
|--------|------|------|
| JotForm | `im@teamo2.kr` (Bitwarden) | 설문 폼 관리 |
| Google Sheets / Drive | `iann@teamo2.kr` | 시트·드라이브 소유자 |

### JotForm 설문 폼

| 환경 | 폼 이름 |
|------|---------|
| prod | 결항 예약 취소 및 환불 접수 |
| dev | [테스트] 결항 예약 취소 및 환불 접수 |

### Slack 채널 · 봇 구성

| 환경 | 봇 | 채널 |
|------|-----|------|
| prod | 알리미 | 카모아_예약이, 카모아_알림_결항확인서 |
| dev | 결항 알리미 테스트 | ai-test |

### DB

정산과 동일한 DB를 공유한다 (스레드 탐색 로직 공용).

### 로컬 테스트 방법

`ai-test` 채널에서 카모아_예약이 스레드 형식의 메시지와 결항확인서 이미지를 직접 올리면, 로컬 서버가 이를 읽고 댓글로 검증 결과를 달아준다.

---

## 필요한 것

- Python 3.12+
- PostgreSQL 16+ (psycopg2 드라이버)
- [uv](https://docs.astral.sh/uv/) (없으면: `curl -LsSf https://astral.sh/uv/install.sh | sh`)

## 셋업

```bash
# 1. 클론
git clone https://github.com/teamo2dev/ai-slackapp.git
cd ai-slackapp

# 2. 의존성 설치
uv sync
uv run pre-commit install

# 3. 환경변수 설정
cp .env.sample .env
```

`.env` 파일을 열고 값을 채운다:

```env
ENVIRONMENT=dev

# Slack (필수)
SLACK_APP_TOKEN=xapp-xxx          # Socket Mode용 App-Level Token
SLACK_BOT_TOKEN=xoxb-xxx          # Bot User OAuth Token
SLACK_SIGNING_SECRET=xxx

# Google Sheets (필수)
GOOGLE_CREDENTIALS_FILE=credentials.json

# PostgreSQL (필수)
DATABASE_USER=postgres
DATABASE_PASSWORD=xxx
DATABASE_HOST=xxx
DATABASE_PORT=5432
DATABASE_DBNAME=postgres

# AI 분석 (결항 기능 사용 시)
GEMINI_API_KEY=xxx
OPENAI_API_KEY=xxx
```

### 4. DB 준비

기존 DB에 접속하는 경우 이 단계를 건너뛰고 `.env`만 채우면 된다.

**새 DB를 만들어야 하는 경우:**

```bash
sudo -u postgres psql -p <port>

CREATE USER <user> WITH PASSWORD '<password>';
CREATE DATABASE <dbname> OWNER <user>;
GRANT ALL PRIVILEGES ON DATABASE <dbname> TO <user>;
\q
```

**마이그레이션 적용:**

```bash
uv run alembic upgrade head
```

### 5. Google 서비스 계정

1. Google Cloud Console에서 서비스 계정 생성
2. JSON 키 파일 다운로드 → 프로젝트 루트에 `credentials.json`으로 저장
3. 대상 스프레드시트에 서비스 계정 이메일을 **편집자**로 추가

### 6. 로컬 테스트

```bash
# 서버 실행 (Socket Mode로 Slack 연결)
uv run python -m app.main
```

- **dev 환경**: `config.dev.yaml` 사용 — 모든 채널이 `C0AANUJGPAB` (ai-test)로 통일
- **Slack App**: api.slack.com > Your Apps 에서 봇 이름/설정 확인
- **Slack App 필요 설정**:
  - Socket Mode 활성화 + App-Level Token (`connections:write`)
  - Event Subscriptions + Interactivity & Shortcuts 활성화
  - Bot Token Scopes: `chat:write`, `channels:history`, `groups:history`, `users:read`, `im:history`, `mpim:history`

## 자주 쓰는 명령어

```bash
# 서버 실행
uv run python -m app.main

# 유닛 테스트
uv run pytest tests/unit -v

# 린팅 + 포매팅
uv run ruff check --fix && uv run ruff format

# DB 마이그레이션 (모델 변경 후)
uv run alembic revision --autogenerate -m "설명"
uv run alembic upgrade head
```

---

## 프로덕션

### 배포

`main` 브랜치에 push하면 GitHub Actions가 자동 배포한다.

```
Push to main → Docker 빌드 → GHCR push → AWS 서버 배포 (docker compose up -d)
```

수동 배포: GitHub Actions > Deploy to Production Server > `workflow_dispatch`.
`force_infra_deploy: true`는 Secret 변경 시 컨테이너 강제 재생성.

### 인프라

| 구성 | 상세 |
|------|------|
| 이미지 레지스트리 | `ghcr.io/teamo2dev/slack-bot` |
| 서버 | AWS EC2 (Bastion Host 경유) |
| 컨테이너 | Docker Compose (`docker-compose.prod.yml`) |
| DB | PostgreSQL |
| 네트워크 | n8n과 Docker network 공유 (`n8n-cloud-tm2-network`) |

### GitHub Secrets

| Secret | 용도 |
|--------|------|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` | SG 임시 허용 |
| `AWS_TM2_BASTION_HOST` / `USERNAME` / `KEY` / `PORT` / `SG` | Bastion Host 접속 |
| `PROD_SERVER_HOST` / `USER` / `KEY` / `PORT` | 프로덕션 서버 접속 |
| `GHCR_PAT` | GitHub Container Registry 인증 |
| `SLACK_APP_TOKEN` / `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET` | Slack |
| `DATABASE_HOST` / `PASSWORD` / `USER` / `PORT` / `DBNAME` | PostgreSQL |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | AI 분석 |
| `JOTFORM_API_KEY` | JotForm 연동 |

### 프로덕션 채널

| 채널 | ID | 용도 |
|------|-----|------|
| 카모아_업체이관 | `C0115V08YS1` | 이관 예약 감지 |
| 정산이슈_확인 | `C0AGV65DXMX` | 승인 요청 포스팅 |
| 카모아_알림_결항확인서 | `C03ACLFMAFN` | 결항 검증 결과 |
| 카모아_예약이 외 6개 | config 참조 | 정산 명령 수신 |

### 프로덕션 시트

| 시트 | 시트명 | 비고 |
|------|--------|------|
| 정산 | `정산용(AI연동)` | header 2행, `정산완료` 체크박스 필수 |
| 이슈로그 | `CS확인용(AI연동)` | header 1행, `sync_key` 헤더 필수 |
| 결항 설문 | `결항데이터` | 설문 응답 폴링 대상 |
| 결항 관리 | `결항관리` | 검증 결과 기록 |

### 로그 확인

```bash
docker logs slack-bot --tail 100 -f
tail -f /var/log/slack-bot/*.log
```

---

## 상세 문서

[`CLAUDE.md`](CLAUDE.md) -- 아키텍처, 레이어 규칙, 에러 핸들링, 테스트 패턴, 코드 스타일

## 커밋 컨벤션

```
TYPE: (TICKET) 설명
# 예: FEAT: (AI-98) 결항 AI 검증 추가
# TYPE: FEAT, FIX, TEST, DOCS, CHORE, REFACTOR
```

## License

Private - Carmore Internal Use Only
