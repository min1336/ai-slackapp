-- 정산완료 컬럼 추가 및 upsert 전략 변경
-- booking_key 단독 unique → booking_key + settlement_completed=FALSE partial unique

ALTER TABLE settlements ADD COLUMN IF NOT EXISTS settlement_completed BOOLEAN DEFAULT FALSE;

-- 기존 booking_key unique 제약 제거
ALTER TABLE settlements DROP CONSTRAINT IF EXISTS settlements_booking_key_key;
DROP INDEX IF EXISTS ix_settlements_booking_key;

-- 활성 건(settlement_completed=FALSE)만 booking_key unique 보장
CREATE UNIQUE INDEX IF NOT EXISTS uq_settlements_booking_key_active
    ON settlements (booking_key) WHERE settlement_completed = FALSE;

-- 전체 booking_key 조회용 일반 인덱스
CREATE INDEX IF NOT EXISTS ix_settlements_booking_key ON settlements (booking_key);
