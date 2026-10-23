-- V22 视频拆解：拆解任务表 + 逐镜结果表

CREATE TABLE video_deconstructions (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    project_id          BIGINT NOT NULL,
    asset_id            BIGINT,
    source_name         VARCHAR(500),
    source_path         VARCHAR(1000) NOT NULL,
    status              VARCHAR(16) NOT NULL,
    error_message       VARCHAR(2000),
    duration_sec        DOUBLE,
    width               INTEGER,
    height              INTEGER,
    fps                 DOUBLE,
    bit_rate            BIGINT,
    shot_count          INTEGER,
    avg_shot_duration_sec DOUBLE,
    cuts_per_minute     DOUBLE,
    rhythm_class        VARCHAR(32),
    hook_end_sec        DOUBLE,
    result_json         CLOB,
    report_md           CLOB,
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP
);

CREATE TABLE video_deconstruction_shots (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    deconstruction_id   BIGINT NOT NULL,
    shot_no             INTEGER NOT NULL,
    start_sec           DOUBLE,
    end_sec             DOUBLE,
    duration_sec        DOUBLE,
    keyframe_path       VARCHAR(1000),
    segment_role        VARCHAR(32),
    duration_class      VARCHAR(32),
    description         VARCHAR(2000),
    shot_size_label     VARCHAR(32),
    camera_move_label   VARCHAR(32),
    prompt_generic      CLOB,
    prompt_seedance     CLOB,
    created_at          TIMESTAMP
);

CREATE INDEX idx_vd_project ON video_deconstructions(project_id);
CREATE INDEX idx_vds_decon ON video_deconstruction_shots(deconstruction_id);
