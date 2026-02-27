# Thread Discovery Backfill Design

## 문제

이관 채널 메시지 도착 시, 예약 채널의 원본 스레드를 찾지 못하고 항상 이관 채널에 폴백 답글이 달린다.

### 근본 원인

1. **콜드 스타트**: 봇 재시작 시 이전에 올라온 예약 메시지의 DB 캐시가 없음
2. **Slack API 한계**: `conversations_history` 순차 탐색은 최대 5,000개 메시지만 조회 가능. 하루 수백 건 채널에서는 일주일이면 한계 초과
3. **이벤트 누락**: 봇 다운타임 동안 올라온 메시지는 캐싱 자체가 안 됨

## 해결 전략

**방식 A: DB 캐시 신뢰도 강화** — 봇 시작 시 백필 + 실시간 캐싱 보강

## 변경 사항

### 1. 봇 시작 시 백필 (Backfill on Startup)

`ThreadDiscoveryService.backfill_reservation_threads(days=7)`:
- `conversations_history`로 예약 채널의 최근 7일 메시지 조회
- 각 메시지에서 `parse_settlement_message(text)` → `booking_key` 추출
- DB에 없는 건만 `ThreadReferenceStore.save()` 저장
- Slack API 에러 시 로그만 남기고 봇 시작은 정상 진행

### 2. `list_channel_messages` 신규 메서드

Protocol `SlackMessageReader`에 추가:

```python
def list_channel_messages(
    self,
    channel_id: str,
    *,
    oldest: float = 0,
    max_pages: int = 50,
) -> Iterator[dict]:
```

- `conversations_history` 페이징, `oldest` 이전 메시지에서 중단
- Iterator로 메모리 효율 확보

### 3. 실시간 캐싱 보강

`_cache_reservation_origin_thread`에서 파싱 실패 시 `logger.debug` 로그 추가.

## 변경 파일

| 파일 | 변경 |
|------|------|
| `app/infrastructure/protocols.py` | `SlackMessageReader`에 `list_channel_messages` 시그니처 추가 |
| `app/infrastructure/slack_client.py` | `list_channel_messages()` raw 함수 추가 |
| `app/services/slack_reader.py` | `list_channel_messages()` 위임 메서드 추가 |
| `app/services/thread_discovery_service.py` | `backfill_reservation_threads()` 메서드 추가 |
| `app/main.py` | 봇 시작 시 백필 호출 |
| `app/listener/messages.py` | 파싱 실패 로깅 추가 |
| `tests/fakes/fake_slack.py` | `FakeSlackReader`에 `list_channel_messages` 구현 |
| `tests/unit/test_thread_discovery_service.py` | 백필 테스트 추가 |

## 에러 핸들링

- 백필 Slack API 에러: 로그 후 봇 시작 정상 진행
- 개별 메시지 파싱 실패: 해당 메시지 스킵, 나머지 계속

## 테스트

- 백필 후 DB에 ThreadReference 저장 검증
- 중복 저장 방지 검증 (이미 있는 건 스킵)
- Slack API 실패 시 봇 시작 정상 진행 검증
