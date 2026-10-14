CREATE TABLE IF NOT EXISTS show_meta (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cue (
    id TEXT PRIMARY KEY,
    show_id TEXT NOT NULL REFERENCES show_meta(id),
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    fade_in_ms INTEGER NOT NULL DEFAULT 0,
    fade_out_ms INTEGER NOT NULL DEFAULT 0,
    fallback_cue_id TEXT,
    notes TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'IDLE',
    ord INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cue_show_ord ON cue(show_id, ord);
