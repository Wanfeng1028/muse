-- AI MV 导入音频模式：mv_songs 加 source 列（AI=AI 创作，IMPORT=导入已有音频）
ALTER TABLE mv_songs ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'AI';
