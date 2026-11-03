-- 用量采集：prompt/completion/cached token 拆分字段，老数据默认 0
ALTER TABLE video_tasks ADD COLUMN prompt_tokens BIGINT DEFAULT 0;
ALTER TABLE video_tasks ADD COLUMN completion_tokens BIGINT DEFAULT 0;
ALTER TABLE video_tasks ADD COLUMN cached_tokens BIGINT DEFAULT 0;
ALTER TABLE agent_steps ADD COLUMN prompt_tokens BIGINT DEFAULT 0;
ALTER TABLE agent_steps ADD COLUMN completion_tokens BIGINT DEFAULT 0;
ALTER TABLE agent_steps ADD COLUMN cached_tokens BIGINT DEFAULT 0;
-- 老数据的 tokens_used 保留不动（历史口径），拆分字段默认 0
