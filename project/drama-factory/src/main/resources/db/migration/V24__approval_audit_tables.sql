-- V24 审批审计补建表；run_approvals/step_attempts 实体自 2026-10-22 存在但无建表迁移，生产启动 validate 失败。

CREATE TABLE run_approvals (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    approved BOOLEAN NOT NULL,
    note VARCHAR(2000),
    decided_by VARCHAR(128),
    decided_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_ra_run ON run_approvals(run_id);

CREATE TABLE step_attempts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    step_id BIGINT NOT NULL,
    attempt_no INTEGER NOT NULL,
    status_before VARCHAR(32),
    status_after VARCHAR(32),
    error_message VARCHAR(2000),
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_sa_step ON step_attempts(step_id);