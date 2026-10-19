package store

import (
	"database/sql"
	"testing"
	"time"
)

func TestJitterScore_Stable(t *testing.T) {
	st, _ := newProfileTestStore(t)
	mid := int64(1)
	now := time.Now().UTC()
	for i := 0; i < 10; i++ {
		_, err := st.InsertCheck(Check{MonitorID: mid, CheckedAt: now.Add(-time.Duration(i) * time.Minute).Format(time.RFC3339), Ok: 1, LatencyMs: 10})
		if err != nil {
			t.Fatal(err)
		}
	}
	score, level, err := st.JitterScore(mid, 30)
	if err != nil {
		t.Fatal(err)
	}
	if score != 0 {
		t.Fatalf("score=%v want 0", score)
	}
	if level != "稳定" {
		t.Fatalf("level=%q want 稳定", level)
	}
}

func TestJitterScore_Flapping(t *testing.T) {
	st, _ := newProfileTestStore(t)
	mid := int64(1)
	now := time.Now().UTC()
	for i := 0; i < 10; i++ {
		ok := 1
		if i%2 == 1 {
			ok = 0
		}
		_, err := st.InsertCheck(Check{MonitorID: mid, CheckedAt: now.Add(-time.Duration(i) * time.Minute).Format(time.RFC3339), Ok: ok, LatencyMs: 10})
		if err != nil {
			t.Fatal(err)
		}
	}
	score, level, err := st.JitterScore(mid, 30)
	if err != nil {
		t.Fatal(err)
	}
	if score != 100 {
		t.Fatalf("score=%v want 100", score)
	}
	if level != "频繁抖动" {
		t.Fatalf("level=%q want 频繁抖动", level)
	}
}

func TestJitterScore_Slight(t *testing.T) {
	st, _ := newProfileTestStore(t)
	mid := int64(1)
	now := time.Now().UTC()
	for i := 0; i < 100; i++ {
		ok := 1
		if i == 99 {
			ok = 0
		}
		_, err := st.InsertCheck(Check{MonitorID: mid, CheckedAt: now.Add(-time.Duration(i) * time.Minute).Format(time.RFC3339), Ok: ok, LatencyMs: 10})
		if err != nil {
			t.Fatal(err)
		}
	}
	score, level, err := st.JitterScore(mid, 30)
	if err != nil {
		t.Fatal(err)
	}
	if diff := score - 1.01; diff > 0.01 || diff < -0.01 {
		t.Fatalf("score=%v want ~1.01", score)
	}
	if level != "轻微波动" {
		t.Fatalf("level=%q want 轻微波动", level)
	}
}

func TestJitterScore_TooFew(t *testing.T) {
	st, _ := newProfileTestStore(t)
	mid := int64(1)
	now := time.Now().UTC()
	_, err := st.InsertCheck(Check{MonitorID: mid, CheckedAt: now.Format(time.RFC3339), Ok: 1, LatencyMs: 10})
	if err != nil {
		t.Fatal(err)
	}
	score, level, err := st.JitterScore(mid, 30)
	if err != nil {
		t.Fatal(err)
	}
	if score != 0 {
		t.Fatalf("score=%v want 0", score)
	}
	if level != "数据不足" {
		t.Fatalf("level=%q want 数据不足", level)
	}
}

func TestIncidentTimeline(t *testing.T) {
	st, db := newProfileTestStore(t)
	mid := int64(1)
	now := time.Now().UTC()
	t1 := now.Add(-3 * time.Hour).Format(time.RFC3339)
	t2 := now.Add(-2 * time.Hour).Format(time.RFC3339)
	t3 := now.Add(-1 * time.Hour).Format(time.RFC3339)
	if _, err := db.Exec(`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error) VALUES (?,?,?,?,?)`, mid, t1, t1, int64(60), ""); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error) VALUES (?,?,?,?,?)`, mid, t2, t2, int64(120), ""); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error) VALUES (?,?,?,?,?)`, mid, t3, nil, nil, "connection refused"); err != nil {
		t.Fatal(err)
	}
	events, err := st.IncidentTimeline(mid, 30, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(events) != 3 {
		t.Fatalf("len=%d want 3", len(events))
	}
	if events[0].StartedAt != t3 {
		t.Fatalf("first started_at=%q want %q", events[0].StartedAt, t3)
	}
	if events[1].StartedAt != t2 {
		t.Fatalf("second started_at=%q want %q", events[1].StartedAt, t2)
	}
	if events[2].StartedAt != t1 {
		t.Fatalf("third started_at=%q want %q", events[2].StartedAt, t1)
	}
	if !events[0].Open {
		t.Fatalf("events[0] should be Open")
	}
	if events[0].DowntimeSec != nil {
		t.Fatalf("open DowntimeSec=%v want nil", events[0].DowntimeSec)
	}
	if events[1].Open {
		t.Fatalf("events[1] should not be Open")
	}
	if v, ok := events[1].DowntimeSec.(int64); !ok || v != 120 {
		t.Fatalf("events[1] DowntimeSec=%v want 120", events[1].DowntimeSec)
	}
	if v, ok := events[2].DowntimeSec.(int64); !ok || v != 60 {
		t.Fatalf("events[2] DowntimeSec=%v want 60", events[2].DowntimeSec)
	}
}

func TestMonitorPortrait(t *testing.T) {
	st, db := newProfileTestStore(t)
	mid := int64(1)
	now := time.Now().UTC()
	for i := 0; i < 10; i++ {
		ok := 1
		if i%3 == 0 {
			ok = 0
		}
		_, err := st.InsertCheck(Check{MonitorID: mid, CheckedAt: now.Add(-time.Duration(i) * time.Minute).Format(time.RFC3339), Ok: ok, LatencyMs: int64(10 + i)})
		if err != nil {
			t.Fatal(err)
		}
	}
	if _, err := db.Exec(`INSERT INTO incidents(monitor_id, started_at, ended_at, downtime_sec, start_error) VALUES (?,?,?,?,?)`, mid, now.Add(-2*time.Hour).Format(time.RFC3339), now.Add(-time.Hour).Format(time.RFC3339), int64(3600), ""); err != nil {
		t.Fatal(err)
	}
	p, err := st.MonitorPortrait(mid)
	if err != nil {
		t.Fatal(err)
	}
	if p.Uptime7d < 0 || p.Uptime7d > 100 {
		t.Fatalf("Uptime7d=%v out of range", p.Uptime7d)
	}
	if p.Uptime30d < 0 || p.Uptime30d > 100 {
		t.Fatalf("Uptime30d=%v out of range", p.Uptime30d)
	}
	if p.LatencyP50 < 0 {
		t.Fatalf("LatencyP50=%v want >=0", p.LatencyP50)
	}
	if len(p.Timeline) == 0 {
		t.Fatalf("Timeline empty")
	}
	if len(p.Daily) != 30 {
		t.Fatalf("Daily len=%d want 30", len(p.Daily))
	}
	if p.JitterLevel == "" {
		t.Fatalf("JitterLevel empty")
	}
	_ = sql.ErrNoRows
}
