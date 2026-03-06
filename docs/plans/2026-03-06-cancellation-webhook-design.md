# Jotform Webhook 기반 결항 처리 설계

## 배경

결항 이미지 처리가 5분 폴링 방식(Google Sheets + Google Drive)으로 동작 중.
리소스 낭비와 지연이 발생하므로 Jotform webhook 기반 즉시 처리로 전환한다.

## 현재 흐름 (제거 대상)

```
Jotform 제출 → Google Sheets 자동 기록
  ↓ (5분 폴링)
SurveySheetReader.get_all_submissions() → 미처리 행 반환
  ↓
DriveImageGateway.find_folder() → Drive 폴더 검색
DriveImageGateway.list_image_files() → 파일 목록
DriveImageGateway.download_file() → 파일 다운로드
  ↓
Slack 스레드에 업로드 → 시트에 처리완료 마킹
```

## 변경 후 흐름

```
Jotform 제출 → POST /webhook/cancellation (HTTP)
  ↓
Webhook 핸들러가 payload 파싱 → SurveySubmission 생성
  ↓
booking_key로 Slack 스레드 검색
  ↓
Jotform URL에서 파일 직접 다운로드 (Drive 불필요)
  ↓
PDF → 이미지 변환 (기존 로직 유지)
  ↓
Slack 스레드에 업로드 + 운영현황 시트 행 추가
  ↓
HTTP 200 응답
```

## 제거 대상

- `_start_cancellation_worker()` (main.py) — 5분 폴링 스레드
- `SurveySheetReader.get_all_submissions()` — 시트 폴링
- `SurveySheetReader.mark_processed()` — 처리완료 마킹
- `DriveImageGateway` 의존성 — Drive 폴더 검색 + 파일 다운로드
- `CancellationImageService._processed_ids` — in-memory 중복 방지 (불필요)

## 유지 대상

- `SurveySheetReader.write_formatted_row()` — 운영현황 시트 작성
- PDF 변환 로직 (`_convert_pdf_to_images`)
- Slack 스레드 검색 + 파일 업로드 로직

## 컴포넌트 설계

### 1. HTTP 서버

- stdlib `http.server.HTTPServer`를 daemon thread로 실행
- `localhost:8080`에서 리슨
- 새 의존성 없음
- Apache 리버스프록시로 외부 노출

### 2. Webhook 핸들러

Jotform POST payload에서 데이터 추출:

| Question ID | 필드 | 용도 |
|-------------|------|------|
| submissionID | submission_id | 고유 식별자 |
| 12 | customer_name | 운전자 성함 |
| 14 | booking_key | 예약번호 |
| 26 | company_name | 업체명 |
| 13 | phone | 전화번호 |
| 11 | file_urls | 결항확인서 파일 URL 목록 |
| 17 | note | 추가 상담 내용 |

### 3. 파일 다운로드

- Jotform URL에서 직접 HTTP GET
- 기존 `DriveImageGateway` 대체
- URL에서 파일명과 MIME type 추론

### 4. 인프라 설정

```
[EC2]
  Apache (:443)
    → ProxyPass /webhook/cancellation → localhost:8080
  Docker (docker-compose.prod.yml)
    slack-bot 컨테이너
      ├── SocketModeHandler (기존, 변경 없음)
      └── HTTP 서버 thread (:8080)
      ports: "8080:8080" 추가
```

## Jotform 설정

- Jotform 폼 Settings → Integrations → Webhooks 추가
- Webhook URL: `https://<도메인>/webhook/cancellation`
- 대상 폼: `220951771126454` (프로덕션), `260620527616454` (테스트)
