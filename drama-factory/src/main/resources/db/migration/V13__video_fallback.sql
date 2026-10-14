-- V13__video_fallback.sql —— 视频通道降级原因字段
ALTER TABLE video_tasks ADD COLUMN fallback_reason VARCHAR(500);
