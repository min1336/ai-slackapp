-- 002: 테이블 리네임 (approval_logs → issue_logs) + 컬럼 추가 (reviewer_name, rejection_reason)

-- 1. 테이블 리네임
ALTER TABLE approval_logs RENAME TO issue_logs;

-- 2. 인덱스 리네임 (존재하는 경우)
ALTER INDEX IF EXISTS ix_approval_logs_sync_status RENAME TO ix_issue_logs_sync_status;

-- 3. settlements 테이블에 컬럼 추가
ALTER TABLE settlements ADD COLUMN IF NOT EXISTS reviewer_name VARCHAR(100) DEFAULT '';
ALTER TABLE settlements ADD COLUMN IF NOT EXISTS rejection_reason TEXT DEFAULT '';

-- 4. issue_logs 테이블에 컬럼 추가
ALTER TABLE issue_logs ADD COLUMN IF NOT EXISTS reviewer_name VARCHAR(100) DEFAULT '';
ALTER TABLE issue_logs ADD COLUMN IF NOT EXISTS rejection_reason TEXT DEFAULT '';
