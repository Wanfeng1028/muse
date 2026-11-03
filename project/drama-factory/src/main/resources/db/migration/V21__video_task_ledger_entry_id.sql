-- 关联 cost_ledger_entry.id，视频提交时预留、轮询完成/失败时结算；null 表示未走账本
ALTER TABLE video_tasks ADD COLUMN ledger_entry_id BIGINT;
