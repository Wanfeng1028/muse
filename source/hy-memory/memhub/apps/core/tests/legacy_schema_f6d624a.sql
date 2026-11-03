-- One Memory 主库在 f6d624a（去掉 candidate 之前）完整启动一次后的表结构。
-- 由 f6d624a 的 create_app lifespan 在空沙箱目录生成，按 sqlite_master 顺序导出，未手改。
-- FTS5 影子表与 sqlite_sequence 由 SQLite 自己建，这里不列。

CREATE TABLE change_outbox (
    event_id TEXT PRIMARY KEY,
    cause TEXT NOT NULL,
    evidence_id TEXT,
    evidence_revision INTEGER,
    permission_epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    notified_at TEXT
);

CREATE TABLE evidence (
    evidence_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    workspace TEXT,
    project TEXT,
    conversation_id TEXT NOT NULL,
    message_id TEXT,
    correlation_id TEXT,
    source_ordinal TEXT,
    content_kind TEXT NOT NULL DEFAULT 'raw_conversation',
    role TEXT NOT NULL,
    written_by TEXT NOT NULL,
    created_at TEXT,
    verbatim TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    revision INTEGER NOT NULL,
    imported_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX evidence_conversation_index
ON evidence(user_id, source_id, conversation_id, workspace, project);

CREATE INDEX evidence_coverage_index
ON evidence(user_id, source_id, conversation_id, written_by, created_at, evidence_id);

CREATE INDEX evidence_workspace_index
ON evidence(user_id, source_id, workspace, project)
WHERE workspace IS NOT NULL;

CREATE TABLE evidence_repairs (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE evidence_origins (
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id) ON DELETE CASCADE,
    origin TEXT NOT NULL,
    raw_meta_json TEXT NOT NULL,
    source_version TEXT,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (evidence_id, origin)
);

CREATE TABLE evidence_versions (
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    verbatim TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    written_by TEXT NOT NULL,
    created_at TEXT,
    changed_at TEXT NOT NULL,
    PRIMARY KEY (evidence_id, revision)
);

CREATE VIRTUAL TABLE evidence_search USING fts5(
    verbatim,
    content='evidence',
    content_rowid='rowid',
    tokenize='trigram'
);

CREATE TRIGGER evidence_search_insert AFTER INSERT ON evidence BEGIN
    INSERT INTO evidence_search(rowid, verbatim) VALUES (new.rowid, new.verbatim);
END;

CREATE TRIGGER evidence_search_delete AFTER DELETE ON evidence BEGIN
    INSERT INTO evidence_search(evidence_search, rowid, verbatim)
    VALUES ('delete', old.rowid, old.verbatim);
END;

CREATE TRIGGER evidence_search_update AFTER UPDATE ON evidence BEGIN
    INSERT INTO evidence_search(evidence_search, rowid, verbatim)
    VALUES ('delete', old.rowid, old.verbatim);
    INSERT INTO evidence_search(rowid, verbatim) VALUES (new.rowid, new.verbatim);
END;

CREATE TABLE trusted_sessions (
    session_key TEXT PRIMARY KEY,
    installation_id TEXT NOT NULL,
    host_id TEXT NOT NULL,
    native_session_id TEXT NOT NULL,
    runtime_instance TEXT NOT NULL,
    workspace TEXT,
    UNIQUE (installation_id, host_id, native_session_id, runtime_instance)
);

CREATE TABLE session_subscriptions (
    session_key TEXT PRIMARY KEY,
    granted_sources TEXT NOT NULL,
    permission_epoch INTEGER NOT NULL
);

CREATE TABLE session_inbox_cursors (
    cursor_token TEXT PRIMARY KEY,
    session_key TEXT NOT NULL,
    scanned_event_id TEXT,
    permission_epoch INTEGER NOT NULL
);

CREATE TABLE session_inbox_batches (
    batch_id TEXT PRIMARY KEY,
    session_key TEXT NOT NULL,
    state TEXT NOT NULL
);

CREATE TABLE session_snapshots (
    snapshot_token TEXT PRIMARY KEY,
    session_key TEXT NOT NULL,
    frozen_ids TEXT NOT NULL
);

CREATE TABLE session_leases (
    session_key TEXT PRIMARY KEY,
    pid INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE call_events (
    event_id TEXT PRIMARY KEY NOT NULL,
    occurred_at TEXT NOT NULL,
    host_id TEXT,
    payload TEXT NOT NULL
);

CREATE INDEX call_events_time ON call_events(occurred_at DESC, event_id DESC);

CREATE INDEX call_events_host_time ON call_events(host_id, occurred_at DESC, event_id DESC);

CREATE TABLE governed_memories (
    memory_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    content TEXT NOT NULL,
    scopes_json TEXT NOT NULL,
    origin TEXT,
    tags_json TEXT,
    revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    undo_cursor_revision INTEGER
);

CREATE INDEX governed_memories_list
ON governed_memories(user_id, status, updated_at DESC, memory_id);

CREATE TABLE governed_memory_versions (
    memory_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    content TEXT NOT NULL,
    scopes_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (memory_id, revision),
    FOREIGN KEY (memory_id) REFERENCES governed_memories(memory_id) ON DELETE CASCADE
);

CREATE TABLE governed_memory_evidence (
    memory_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (memory_id, evidence_id),
    FOREIGN KEY (memory_id) REFERENCES governed_memories(memory_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id)
);

CREATE TABLE governed_memory_mutations (
    user_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    result_revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, request_id)
);

CREATE TABLE memory_deletions (
    memory_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    checkpoint INTEGER NOT NULL DEFAULT 0,
    runner_token TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES governed_memories(memory_id) ON DELETE CASCADE
);

CREATE TABLE memory_index_syncs (
    memory_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES governed_memories(memory_id) ON DELETE CASCADE
);

CREATE TABLE import_jobs (
    job_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    status TEXT NOT NULL,
    phase TEXT,
    runner_token TEXT,
    heartbeat_at TEXT,
    checkpoint TEXT,
    discovered INTEGER NOT NULL DEFAULT 0,
    discovered_targets INTEGER NOT NULL DEFAULT 0,
    emitted INTEGER NOT NULL DEFAULT 0,
    stored INTEGER NOT NULL DEFAULT 0,
    revised INTEGER NOT NULL DEFAULT 0,
    merged INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
, "operation" TEXT NOT NULL DEFAULT 'history');

CREATE TABLE import_issues (
    issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES import_jobs(job_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    conversation_id TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE import_skip_reason_counts (
    job_id TEXT NOT NULL REFERENCES import_jobs(job_id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (job_id, reason)
);

CREATE TABLE source_cursors (
    user_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    file_key TEXT NOT NULL,
    file_identity TEXT NOT NULL,
    checkpoint TEXT NOT NULL,
    checkpoint_anchor TEXT,
    observed_size INTEGER NOT NULL,
    observed_modified_ns INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, source_id, file_key)
);

CREATE UNIQUE INDEX one_active_import_per_source
                ON import_jobs(user_id, source_id, operation)
                WHERE status IN ('pending', 'running', 'paused', 'interrupted', 'failed')
                ;

CREATE TABLE onboarding_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    status TEXT NOT NULL,
    selected_source_ids_json TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE extraction_settings (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    window_preset TEXT NOT NULL
);

CREATE TABLE source_grants (
    user_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    root_path TEXT NOT NULL,
    candidate_kind TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    revoked_at TEXT,
    PRIMARY KEY (user_id, source_id)
);

CREATE TABLE source_candidates (
    user_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    requested_path TEXT NOT NULL,
    root_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, source_id)
);

CREATE TABLE model_profiles (
    profile_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider_kind TEXT NOT NULL,
    base_url TEXT,
    model TEXT NOT NULL,
    embedding_model TEXT,
    embedding_provider_kind TEXT,
    embedding_base_url TEXT,
    embedding_dimensions INTEGER,
    secret_ref TEXT,
    timeout_seconds INTEGER NOT NULL,
    max_concurrency INTEGER NOT NULL,
    context_window INTEGER,
    disable_thinking INTEGER NOT NULL DEFAULT 1,
    endpoint_reachable INTEGER NOT NULL DEFAULT 0,
    model_available INTEGER NOT NULL DEFAULT 0,
    structured_output INTEGER NOT NULL DEFAULT 0,
    embedding_available INTEGER NOT NULL DEFAULT 0,
    revision INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX one_active_model_profile
ON model_profiles(is_active) WHERE is_active = 1;

CREATE TABLE model_profile_versions (
    profile_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    provider_kind TEXT NOT NULL,
    base_url TEXT,
    model TEXT NOT NULL,
    embedding_model TEXT,
    embedding_provider_kind TEXT,
    embedding_base_url TEXT,
    embedding_dimensions INTEGER,
    timeout_seconds INTEGER NOT NULL,
    max_concurrency INTEGER NOT NULL,
    context_window INTEGER,
    disable_thinking INTEGER NOT NULL DEFAULT 0,
    secret_ref TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, revision),
    FOREIGN KEY (profile_id) REFERENCES model_profiles(profile_id) ON DELETE CASCADE
);

CREATE TABLE matter_versions(
    matter_id TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL,
    dependencies TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(matter_id,version)
);

CREATE TABLE matters(
    matter_id TEXT PRIMARY KEY, version INTEGER NOT NULL, needs_update INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE matter_notes(
    matter_id TEXT NOT NULL, evidence_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
);

CREATE TABLE matter_runs(
    run_id TEXT PRIMARY KEY, body TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE matter_memory_dependencies(
    matter_id TEXT NOT NULL, version INTEGER NOT NULL, memory_id TEXT NOT NULL,
    body TEXT NOT NULL, PRIMARY KEY(matter_id, version, memory_id)
);

CREATE TABLE matter_generation_keys(
    generation_key TEXT PRIMARY KEY, matter_id TEXT NOT NULL
);

CREATE TABLE matter_model_cache (cache_key TEXT PRIMARY KEY, body TEXT NOT NULL);

CREATE TABLE memory_tasks (
    task_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    input_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    profile_revision INTEGER NOT NULL,
    profile_snapshot_json TEXT NOT NULL,
    runner_token TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    duration_seconds REAL,
    UNIQUE (user_id, kind, request_id)
);

CREATE INDEX memory_tasks_status
ON memory_tasks(status, created_at);

CREATE TABLE memory_task_extractions (
    task_id TEXT PRIMARY KEY REFERENCES memory_tasks(task_id) ON DELETE CASCADE,
    content TEXT,
    layer TEXT,
    created_at TEXT NOT NULL,
    CHECK (
        (content IS NULL AND layer IS NULL)
        OR (content IS NOT NULL AND layer IS NOT NULL)
    )
);

CREATE TABLE memory_task_inputs (
    task_id TEXT PRIMARY KEY, refs_json TEXT NOT NULL
);

CREATE TABLE memory_task_outputs (
    task_id TEXT NOT NULL, memory_id TEXT NOT NULL, body TEXT NOT NULL,
    PRIMARY KEY(task_id, memory_id)
);

CREATE INDEX memory_task_outputs_memory ON memory_task_outputs(memory_id);

CREATE TABLE memory_task_contexts (
    task_id TEXT PRIMARY KEY, refs_json TEXT NOT NULL
);

CREATE TABLE model_content_permissions (
    user_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    revocation_revision INTEGER NOT NULL CHECK (revocation_revision >= 0),
    granted_at TEXT NOT NULL,
    revoked_at TEXT,
    snapshot_json TEXT NOT NULL,
    PRIMARY KEY (user_id, revision)
);

CREATE TABLE model_content_evidence_additions (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    invalidated INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE model_content_previews (
    preview_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
    expected_revision INTEGER NOT NULL, expires_at TEXT NOT NULL,
    snapshot_json TEXT NOT NULL
);

CREATE TRIGGER model_content_track_evidence_addition
AFTER INSERT ON evidence BEGIN
    INSERT INTO model_content_evidence_additions (
        evidence_id, user_id, source_id, revision, content_hash, imported_at
    ) VALUES (
        new.evidence_id, new.user_id, new.source_id, new.revision,
        new.content_hash, new.imported_at
    ) ON CONFLICT(evidence_id) DO NOTHING;
END;

CREATE TRIGGER model_content_invalidate_evidence_update
AFTER UPDATE ON evidence
WHEN old.evidence_id IS NOT new.evidence_id OR old.user_id IS NOT new.user_id
    OR old.source_id IS NOT new.source_id OR old.workspace IS NOT new.workspace
    OR old.project IS NOT new.project OR old.conversation_id IS NOT new.conversation_id
    OR old.message_id IS NOT new.message_id OR old.correlation_id IS NOT new.correlation_id
    OR old.source_ordinal IS NOT new.source_ordinal OR old.content_kind IS NOT new.content_kind
    OR old.role IS NOT new.role OR old.written_by IS NOT new.written_by
    OR old.created_at IS NOT new.created_at OR old.verbatim IS NOT new.verbatim
    OR old.content_hash IS NOT new.content_hash OR old.revision IS NOT new.revision
    OR old.imported_at IS NOT new.imported_at
BEGIN
    UPDATE model_content_evidence_additions SET invalidated=1
    WHERE evidence_id=old.evidence_id;
END;

CREATE TRIGGER model_content_invalidate_evidence_delete
AFTER DELETE ON evidence BEGIN
    INSERT INTO model_content_evidence_additions (
        evidence_id, user_id, source_id, revision, content_hash, imported_at, invalidated
    ) VALUES (
        old.evidence_id, old.user_id, old.source_id, old.revision,
        old.content_hash, old.imported_at, 1
    ) ON CONFLICT(evidence_id) DO UPDATE SET invalidated=1;
END;

CREATE TRIGGER model_content_invalidate_origin_update
AFTER UPDATE ON evidence_origins
WHEN old.evidence_id IS NOT new.evidence_id OR old.origin IS NOT new.origin
    OR old.raw_meta_json IS NOT new.raw_meta_json OR old.source_version IS NOT new.source_version
BEGIN
    UPDATE model_content_evidence_additions SET invalidated=1
    WHERE evidence_id IN (old.evidence_id, new.evidence_id);
END;

CREATE TRIGGER model_content_invalidate_origin_delete
AFTER DELETE ON evidence_origins BEGIN
    UPDATE model_content_evidence_additions SET invalidated=1
    WHERE evidence_id=old.evidence_id;
END;

CREATE TRIGGER model_content_invalidate_later_origin
AFTER INSERT ON evidence_origins
WHEN new.observed_at IS NOT (
    SELECT imported_at FROM model_content_evidence_additions WHERE evidence_id=new.evidence_id
)
BEGIN
    UPDATE model_content_evidence_additions SET invalidated=1
    WHERE evidence_id=new.evidence_id;
END;

CREATE TABLE model_content_scope_seals (
    user_id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot_hash TEXT NOT NULL,
    schema_version INTEGER NOT NULL, valid INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(user_id, revision)
);

CREATE TABLE model_content_scope_members (
    user_id TEXT NOT NULL, revision INTEGER NOT NULL, evidence_id TEXT NOT NULL,
    PRIMARY KEY(user_id, revision, evidence_id)
);

CREATE INDEX model_content_scope_members_evidence
ON model_content_scope_members(evidence_id, user_id, revision);

CREATE TRIGGER model_content_seal_evidence_update AFTER UPDATE ON evidence WHEN old.evidence_id IS NOT new.evidence_id OR old.user_id IS NOT new.user_id OR old.source_id IS NOT new.source_id OR old.workspace IS NOT new.workspace OR old.project IS NOT new.project OR old.conversation_id IS NOT new.conversation_id OR old.message_id IS NOT new.message_id OR old.correlation_id IS NOT new.correlation_id OR old.source_ordinal IS NOT new.source_ordinal OR old.content_kind IS NOT new.content_kind OR old.role IS NOT new.role OR old.written_by IS NOT new.written_by OR old.created_at IS NOT new.created_at OR old.verbatim IS NOT new.verbatim OR old.content_hash IS NOT new.content_hash OR old.revision IS NOT new.revision OR old.imported_at IS NOT new.imported_at BEGIN UPDATE model_content_scope_seals SET valid=0 WHERE valid=1 AND (user_id, revision) IN (SELECT user_id, revision FROM model_content_scope_members WHERE evidence_id IN (old.evidence_id,new.evidence_id)); END;

CREATE TRIGGER model_content_seal_evidence_delete AFTER DELETE ON evidence BEGIN UPDATE model_content_scope_seals SET valid=0 WHERE valid=1 AND (user_id, revision) IN (SELECT user_id, revision FROM model_content_scope_members WHERE evidence_id IN (old.evidence_id)); END;

CREATE TRIGGER model_content_seal_origin_update AFTER UPDATE ON evidence_origins WHEN old.evidence_id IS NOT new.evidence_id OR old.origin IS NOT new.origin OR old.raw_meta_json IS NOT new.raw_meta_json OR old.source_version IS NOT new.source_version BEGIN UPDATE model_content_scope_seals SET valid=0 WHERE valid=1 AND (user_id, revision) IN (SELECT user_id, revision FROM model_content_scope_members WHERE evidence_id IN (old.evidence_id,new.evidence_id)); END;

CREATE TRIGGER model_content_seal_origin_delete AFTER DELETE ON evidence_origins BEGIN UPDATE model_content_scope_seals SET valid=0 WHERE valid=1 AND (user_id, revision) IN (SELECT user_id, revision FROM model_content_scope_members WHERE evidence_id IN (old.evidence_id)); END;

CREATE TRIGGER model_content_seal_origin_insert AFTER INSERT ON evidence_origins BEGIN UPDATE model_content_scope_seals SET valid=0 WHERE valid=1 AND (user_id, revision) IN (SELECT user_id, revision FROM model_content_scope_members WHERE evidence_id IN (new.evidence_id)); END;

CREATE TRIGGER model_content_seal_members_delete AFTER DELETE ON model_content_scope_members BEGIN UPDATE model_content_scope_seals SET valid=0 WHERE user_id=old.user_id AND revision=old.revision; END;

CREATE TRIGGER model_content_seal_members_update AFTER UPDATE ON model_content_scope_members BEGIN UPDATE model_content_scope_seals SET valid=0 WHERE (user_id=old.user_id AND revision=old.revision) OR (user_id=new.user_id AND revision=new.revision); END;

CREATE TABLE memory_task_model_permissions (
                    task_id TEXT PRIMARY KEY REFERENCES memory_tasks(task_id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,
                    permission_revision INTEGER NOT NULL,
                    revocation_revision INTEGER NOT NULL,
                    profile_id TEXT NOT NULL,
                    profile_revision INTEGER NOT NULL
                );

CREATE TABLE processing_requests (
        request_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        permission_revision INTEGER NOT NULL CHECK(permission_revision >= 1),
        revocation_revision INTEGER NOT NULL CHECK(revocation_revision >= 0),
        profile_id TEXT NOT NULL,
        profile_revision INTEGER NOT NULL CHECK(profile_revision >= 1),
        state TEXT NOT NULL
            CHECK(state IN ('queued','preparing','prepared','failed','interrupted')),
        safe_error_code TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(user_id, permission_revision, revocation_revision)
    );

CREATE INDEX processing_requests_resumable ON processing_requests(state, created_at, request_id);

CREATE TABLE source_connection_intents (
    user_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    accepted_json TEXT NOT NULL,
    failed_json TEXT NOT NULL,
    job_ids_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(user_id, request_id)
);
