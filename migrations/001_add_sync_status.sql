-- Migration: Add sync_status column for duplicate prevention
-- Run this SQL on your PostgreSQL database before deploying the new code

-- Add sync_status column to settlements table
ALTER TABLE settlements
ADD COLUMN IF NOT EXISTS sync_status VARCHAR(20) DEFAULT 'pending';

-- Add sync_status column to approval_logs table
ALTER TABLE approval_logs
ADD COLUMN IF NOT EXISTS sync_status VARCHAR(20) DEFAULT 'pending';

-- Update existing synced records to 'completed'
UPDATE settlements SET sync_status = 'completed' WHERE sheets_synced = TRUE;
UPDATE approval_logs SET sync_status = 'completed' WHERE sheets_synced = TRUE;

-- Create index for faster lookup of pending records
CREATE INDEX IF NOT EXISTS idx_settlements_sync_status ON settlements(sync_status) WHERE sync_status = 'pending';
CREATE INDEX IF NOT EXISTS idx_approval_logs_sync_status ON approval_logs(sync_status) WHERE sync_status = 'pending';
