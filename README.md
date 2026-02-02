# Slack 정산 이슈 봇

Slack 스레드에서 정산 이슈를 등록하고 승인/반려 워크플로우를 처리하는 봇입니다.

## Quick Start

### 1. 의존성 설치

```bash
# uv 사용 (권장)
uv sync

# 또는 pip 사용
pip install -e .
```

### 2. Pre-commit 설정

```bash
uv run pre-commit install
```

커밋 시 자동으로 ruff 린팅과 포맷팅이 실행됩니다. `uv run ruff check --fix`와 동일하지만, 커밋할 때 자동 실행되어 문제 있는 코드가 커밋되는 것을 방지합니다.

### 3. 환경변수 설정

```bash
cp .env.sample .env
```

`.env` 파일을 열고 값을 설정합니다:

```env
# Slack App 설정 (필수)
SLACK_APP_TOKEN=xapp-xxx          # App-Level Token (Socket Mode용)
SLACK_BOT_TOKEN=xoxb-xxx          # Bot User OAuth Token
SLACK_SIGNING_SECRET=xxx          # Signing Secret (선택)

# Google Sheets 설정 (필수)
GOOGLE_CREDENTIALS_FILE=credentials.json

# PostgreSQL 설정 (선택 - Supabase 사용 시)
DATABASE_HOST=db.xxx.supabase.co
DATABASE_PASSWORD=xxx
DATABASE_USER=postgres
DATABASE_PORT=5432
DATABASE_DBNAME=postgres
```

> **Note**: DATABASE_HOST와 DATABASE_PASSWORD가 설정되면 PostgreSQL 캐시 레이어가 활성화됩니다. 미설정 시 Google Sheets만 사용합니다.

### 4. 앱 설정 (config.yaml)

`config.yaml` 파일에서 승인자, 스프레드시트, 채널을 설정합니다:

```yaml
# 승인자 슬랙 UserID
approvers:
  - U12345678
  - U87654321

# 슬랙 채널 ID (이관 예약 자동 감지용)
slack_channels:
  transfer_reservation: "C0XXXXXXXX"

# Spread Sheet ID
# https://docs.google.com/spreadsheets/d/{id} 에서 id 추출
spreadsheet:
  id: "your_spreadsheet_id"
  sheets:
    settlement: "정산"
    approval_log: "승인로그"
```

### 5. Google Sheets 서비스 계정 설정

1. Google Cloud Console에서 서비스 계정 생성
2. JSON 키 파일 다운로드 → 프로젝트 루트에 `credentials.json`으로 저장
3. 스프레드시트에서 서비스 계정 이메일을 편집자로 추가

### 6. 실행

```bash
# uv 사용
uv run python -m app.main

# 또는 직접 실행
python -m app.main
```

### 7. 테스트

```bash
# 전체 테스트
pytest tests -v

# 유닛 테스트만 (빠름)
pytest tests/unit -v

# 통합 테스트만 (Google Sheets 연동 테스트)
# 실제로 구글시트에 추가되니 주의해야 할 필요가 있음
pytest tests/integration -v
```
---

## 프로젝트 구조

```
app/
├── main.py                 # 앱 진입점
├── config.py               # 환경변수 설정
├── constants/              # 상수 (옵션, ID, UI 텍스트)
├── models/                 # 데이터 모델
├── listener/               # Slack 이벤트 핸들러 (Controller)
├── services/               # 비즈니스 로직
├── infrastructure/         # 외부 시스템 연동
└── views/                  # Slack Block Kit 빌더

tests/
├── unit/                   # 유닛 테스트
└── integration/            # 통합 테스트
```

### 레이어 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                      listener/                          │
│              (Controller - 요청/응답 처리)               │
├─────────────────────────────────────────────────────────┤
│         services/                    views/             │
│     (비즈니스 로직)              (UI 블록 생성)           │
├─────────────────────────────────────────────────────────┤
│                   infrastructure/                       │
│              (외부 시스템 통신)                          │
├─────────────────────────────────────────────────────────┤
│                      models/                            │
│                   (데이터 모델)                          │
└─────────────────────────────────────────────────────────┘
```

| 레이어 | 역할 | 호출 가능 | 경계 |
|--------|------|----------|------|
| **listener/** | Slack 이벤트 수신, 응답 반환 | services, views, models | infrastructure 직접 호출 금지 |
| **services/** | 비즈니스 로직 | infrastructure, models | listener 호출 금지 |
| **infrastructure/** | 외부 시스템 통신 (Slack API, Google Sheets) | models | 비즈니스 로직 포함 금지 |
| **views/** | Slack Block Kit JSON 생성 | models | 데이터 가공 금지 |
| **models/** | 데이터 구조 정의 | (없음) | 모든 레이어에서 import 가능 |

**원칙: 레이어를 건너뛰어 호출하지 않는다** (listener → ~~infrastructure~~ 금지)

### 데이터 모델 선택 기준

| 기준 | Pydantic | dataclass |
|------|----------|-----------|
| JSON 직렬화 필요 | O | X |
| 필드 검증/변환 필요 | O | X |
| 외부 입력 처리 | O | X |
| 단순 데이터 홀더 | X | O |

```python
# Pydantic - Slack 버튼 value 등 JSON 변환 필요시
data = SettlementData.model_validate_json(button_value)
button_value = data.model_dump_json()

# dataclass - 내부 데이터 변환만 (스프레드시트 행 등)
row = SettlementRow(...)
row.to_row()  # → ["2025-01-28", "작성자", ...]
```

## Slack App 설정

### 필요한 Bot Token Scopes

- `chat:write` - 메시지 전송
- `channels:history` - 채널 메시지 읽기
- `groups:history` - 비공개 채널 메시지 읽기
- `users:read` - 사용자 정보 조회
- `im:history` - DM 메시지 읽기
- `mpim:history`

### Socket Mode

이 봇은 Socket Mode를 사용합니다. Slack App 설정에서:

1. **Settings > Socket Mode** 활성화
2. **App-Level Token** 생성 (`connections:write` scope)
3. **Event Subscriptions** 활성화
4. **Interactivity & Shortcuts** 활성화

### Slack UI Block Kit Builder
[Block Kit Builder](https://app.slack.com/block-kit-builder/T07JC381Y#%7B%22blocks%22:%5B%7B%22type%22:%22section%22,%22text%22:%7B%22type%22:%22mrkdwn%22,%22text%22:%22Hello,%20Assistant%20to%20the%20Regional%20Manager%20Dwight!%20*Michael%20Scott*%20wants%20to%20know%20where%20you'd%20like%20to%20take%20the%20Paper%20Company%20investors%20to%20dinner%20tonight.%5Cn%5Cn%20*Please%20select%20a%20restaurant:*%22%7D%7D,%7B%22type%22:%22divider%22%7D,%7B%22type%22:%22section%22,%22text%22:%7B%22type%22:%22mrkdwn%22,%22text%22:%22*Farmhouse%20Thai%20Cuisine*%5Cn:star::star::star::star:%201528%20reviews%5Cn%20They%20do%20have%20some%20vegan%20options,%20like%20the%20roti%20and%20curry,%20plus%20they%20have%20a%20ton%20of%20salad%20stuff%20and%20noodles%20can%20be%20ordered%20without%20meat!!%20They%20have%20something%20for%20everyone%20here%22%7D,%22accessory%22:%7B%22type%22:%22image%22,%22image_url%22:%22https://s3-media3.fl.yelpcdn.com/bphoto/c7ed05m9lC2EmA3Aruue7A/o.jpg%22,%22alt_text%22:%22alt%20text%20for%20image%22%7D%7D,%7B%22type%22:%22section%22,%22text%22:%7B%22type%22:%22mrkdwn%22,%22text%22:%22*Kin%20Khao*%5Cn:star::star::star::star:%201638%20reviews%5Cn%20The%20sticky%20rice%20also%20goes%20wonderfully%20with%20the%20caramelized%20pork%20belly,%20which%20is%20absolutely%20melt-in-your-mouth%20and%20so%20soft.%22%7D,%22accessory%22:%7B%22type%22:%22image%22,%22image_url%22:%22https://s3-media2.fl.yelpcdn.com/bphoto/korel-1YjNtFtJlMTaC26A/o.jpg%22,%22alt_text%22:%22alt%20text%20for%20image%22%7D%7D,%7B%22type%22:%22section%22,%22text%22:%7B%22type%22:%22mrkdwn%22,%22text%22:%22*Ler%20Ros*%5Cn:star::star::star::star:%202082%20reviews%5Cn%20I%20would%20really%20recommend%20the%20%20Yum%20Koh%20Moo%20Yang%20-%20Spicy%20lime%20dressing%20and%20roasted%20quick%20marinated%20pork%20shoulder,%20basil%20leaves,%20chili%20&%20rice%20powder.%22%7D,%22accessory%22:%7B%22type%22:%22image%22,%22image_url%22:%22https://s3-media2.fl.yelpcdn.com/bphoto/DawwNigKJ2ckPeDeDM7jAg/o.jpg%22,%22alt_text%22:%22alt%20text%20for%20image%22%7D%7D,%7B%22type%22:%22divider%22%7D,%7B%22type%22:%22actions%22,%22elements%22:%5B%7B%22type%22:%22button%22,%22text%22:%7B%22type%22:%22plain_text%22,%22text%22:%22Farmhouse%22,%22emoji%22:true%7D,%22value%22:%22click_me_123%22%7D,%7B%22type%22:%22button%22,%22text%22:%7B%22type%22:%22plain_text%22,%22text%22:%22Kin%20Khao%22,%22emoji%22:true%7D,%22value%22:%22click_me_123%22,%22url%22:%22https://google.com%22%7D,%7B%22type%22:%22button%22,%22text%22:%7B%22type%22:%22plain_text%22,%22text%22:%22Ler%20Ros%22,%22emoji%22:true%7D,%22value%22:%22click_me_123%22,%22url%22:%22https://google.com%22%7D%5D%7D%5D%7D)
해당 링크를 통해 UI를 직접 구성하고 JSON을 사용할 수 있습니다.