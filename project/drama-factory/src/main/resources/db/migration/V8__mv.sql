-- AI MV 模式：mv_songs 表
CREATE TABLE mv_songs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT,
    theme VARCHAR(500) NOT NULL,
    mood VARCHAR(100),
    style VARCHAR(100),
    lyrics_json TEXT,
    audio_url VARCHAR(1000),
    duration_ms INTEGER,
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX idx_mv_songs_run_id ON mv_songs(run_id);
