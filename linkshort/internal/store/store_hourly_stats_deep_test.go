package store

import (
	"testing"
	"time"
)

func insertVisit(t *testing.T, s *Store, linkID int64, ts string) {
	t.Helper()
	_, err := s.db.Exec(
		"INSERT INTO visits (link_id, ts, ip_hash, ua, referer, country_code, country_name, province, city) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
		linkID, ts, "h", "ua", "", "", "", "", "",
	)
	if err != nil {
		t.Fatalf("insert visit: %v", err)
	}
}

func TestHourlyStats_小时分布(t *testing.T) {
	s := newTestStore(t)
	id, err := s.CreateLinkEx("hr1", "https://example.com", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}
	insertVisit(t, s, id, "2026-10-19T03:15:00Z")
	insertVisit(t, s, id, "2026-10-19T03:45:00Z")
	insertVisit(t, s, id, "2026-10-19T15:00:00Z")
	insertVisit(t, s, id, "2026-10-19T15:30:00Z")
	insertVisit(t, s, id, "2026-10-19T15:59:00Z")

	hs, err := s.HourlyStats(id, 0)
	if err != nil {
		t.Fatalf("hourly stats: %v", err)
	}
	if len(hs.Hours) != 24 {
		t.Fatalf("Hours len = %d, want 24", len(hs.Hours))
	}
	if len(hs.Weekdays) != 7 {
		t.Fatalf("Weekdays len = %d, want 7", len(hs.Weekdays))
	}
	if hs.Hours[3] != 2 {
		t.Fatalf("Hours[3] = %d, want 2", hs.Hours[3])
	}
	if hs.Hours[15] != 3 {
		t.Fatalf("Hours[15] = %d, want 3", hs.Hours[15])
	}
	for i, v := range hs.Hours {
		if i == 3 || i == 15 {
			continue
		}
		if v != 0 {
			t.Fatalf("Hours[%d] = %d, want 0", i, v)
		}
	}
	if hs.Total != 5 {
		t.Fatalf("Total = %d, want 5", hs.Total)
	}
}

func TestHourlyStats_星期分布(t *testing.T) {
	s := newTestStore(t)
	id, err := s.CreateLinkEx("wd1", "https://example.com", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}
	insertVisit(t, s, id, "2026-10-19T03:00:00Z")
	insertVisit(t, s, id, "2026-10-19T04:00:00Z")
	insertVisit(t, s, id, "2026-10-18T10:00:00Z")

	hs, err := s.HourlyStats(id, 0)
	if err != nil {
		t.Fatalf("hourly stats: %v", err)
	}
	if hs.Weekdays[1] != 2 {
		t.Fatalf("Weekdays[1] = %d, want 2", hs.Weekdays[1])
	}
	if hs.Weekdays[0] != 1 {
		t.Fatalf("Weekdays[0] = %d, want 1", hs.Weekdays[0])
	}
}

func TestHourlyStats_按链过滤(t *testing.T) {
	s := newTestStore(t)
	id1, err := s.CreateLinkEx("fl1", "https://example.com/a", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}
	id2, err := s.CreateLinkEx("fl2", "https://example.com/b", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}
	insertVisit(t, s, id1, "2026-10-19T03:00:00Z")
	insertVisit(t, s, id1, "2026-10-19T03:10:00Z")
	insertVisit(t, s, id2, "2026-10-19T03:20:00Z")

	hs, err := s.HourlyStats(id1, 0)
	if err != nil {
		t.Fatalf("hourly stats: %v", err)
	}
	if hs.Total != 2 {
		t.Fatalf("Total = %d, want 2", hs.Total)
	}
	if hs.Hours[3] != 2 {
		t.Fatalf("Hours[3] = %d, want 2", hs.Hours[3])
	}
}

func TestHourlyStats_days过滤(t *testing.T) {
	s := newTestStore(t)
	id, err := s.CreateLinkEx("dy1", "https://example.com", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}
	old := nowUTC().AddDate(0, 0, -40).Format(time.RFC3339)
	recent := nowUTC().Format(time.RFC3339)
	insertVisit(t, s, id, old)
	insertVisit(t, s, id, recent)

	hs30, err := s.HourlyStats(id, 30)
	if err != nil {
		t.Fatalf("hourly stats days=30: %v", err)
	}
	if hs30.Total != 1 {
		t.Fatalf("days=30 Total = %d, want 1", hs30.Total)
	}

	hs0, err := s.HourlyStats(id, 0)
	if err != nil {
		t.Fatalf("hourly stats days=0: %v", err)
	}
	if hs0.Total != 2 {
		t.Fatalf("days=0 Total = %d, want 2", hs0.Total)
	}
}

func TestHourlyStats_空库(t *testing.T) {
	s := newTestStore(t)
	hs, err := s.HourlyStats(0, 0)
	if err != nil {
		t.Fatalf("hourly stats: %v", err)
	}
	if len(hs.Hours) != 24 {
		t.Fatalf("Hours len = %d, want 24", len(hs.Hours))
	}
	if len(hs.Weekdays) != 7 {
		t.Fatalf("Weekdays len = %d, want 7", len(hs.Weekdays))
	}
	for i, v := range hs.Hours {
		if v != 0 {
			t.Fatalf("Hours[%d] = %d, want 0", i, v)
		}
	}
	if hs.Total != 0 {
		t.Fatalf("Total = %d, want 0", hs.Total)
	}
}
