
-- AI MV v2：时间轴对齐，mv_songs 加 timeline_json（存 MvTimelineService.toJson 产出）
ALTER TABLE mv_songs ADD COLUMN timeline_json TEXT;
