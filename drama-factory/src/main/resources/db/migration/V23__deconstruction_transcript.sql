-- V23 视频拆解逐字稿：任务表加字幕状态/轨道信息/逐字稿 JSON，逐镜表加该镜字幕文本
ALTER TABLE video_deconstructions ADD COLUMN transcript_status VARCHAR(16);
ALTER TABLE video_deconstructions ADD COLUMN transcript_track_info VARCHAR(200);
ALTER TABLE video_deconstructions ADD COLUMN transcript_json CLOB;
ALTER TABLE video_deconstruction_shots ADD COLUMN transcript_text CLOB;
