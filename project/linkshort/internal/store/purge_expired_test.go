package store

import (
	"database/sql"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
)

func TestPurgeExpiredLinks(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()
	s := New(database)

	now := nowUTC()

	// 1) 已过期 10 天：retention 7 天时删除。
	past10d := now.Add(-10 * 24 * time.Hour)
	idExpired, err := s.CreateLinkEx("expired10d", "https://example.com/a", "t", &past10d, nil, false, false)
	if err != nil {
		t.Fatalf("create expired10d: %v", err)
	}

	// 2) 刚过期 1 小时：retention 7 天时不删。
	past1h := now.Add(-1 * time.Hour)
	if _, err := s.CreateLinkEx("expired1h", "https://example.com/b", "t", &past1h, nil, false, false); err != nil {
		t.Fatalf("create expired1h: %v", err)
	}

	// 3) 未过期：不删。
	future := now.Add(24 * time.Hour)
	if _, err := s.CreateLinkEx("future", "https://example.com/c", "t", &future, nil, false, false); err != nil {
		t.Fatalf("create future: %v", err)
	}

	// 4) expires_at=nil：不删。
	if _, err := s.CreateLinkEx("forever", "https://example.com/d", "t", nil, nil, false, false); err != nil {
		t.Fatalf("create forever: %v", err)
	}

	// 给将被删除的链插一条 visit，验证级联删除。
	if _, err := database.Exec(
		`INSERT INTO visits (link_id, ts) VALUES (?, ?)`,
		idExpired, formatTime(now),
	); err != nil {
		t.Fatalf("insert visit: %v", err)
	}

	before := now.Add(-7 * 24 * time.Hour)
	n, err := s.PurgeExpiredLinks(before)
	if err != nil {
		t.Fatalf("purge: %v", err)
	}
	if n != 1 {
		t.Fatalf("want 1 deleted, got %d", n)
	}

	var cnt int64
	if err := database.QueryRow(`SELECT COUNT(*) FROM links`).Scan(&cnt); err != nil {
		t.Fatalf("count links: %v", err)
	}
	if cnt != 3 {
		t.Fatalf("want 3 links remaining, got %d", cnt)
	}

	var vcnt int64
	if err := database.QueryRow(`SELECT COUNT(*) FROM visits WHERE link_id = ?`, idExpired).Scan(&vcnt); err != nil && err != sql.ErrNoRows {
		t.Fatalf("count visits: %v", err)
	}
	if vcnt != 0 {
		t.Fatalf("want 0 visits for purged link, got %d", vcnt)
	}
}

func TestPurgeExpiredLinks_Boundary(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()
	s := New(database)

	before := nowUTC().Add(-7 * 24 * time.Hour)

	// expires_at == before 整点：严格小于才删，故不删。
	if _, err := s.CreateLinkEx("boundary", "https://example.com/x", "t", &before, nil, false, false); err != nil {
		t.Fatalf("create boundary: %v", err)
	}

	n, err := s.PurgeExpiredLinks(before)
	if err != nil {
		t.Fatalf("purge: %v", err)
	}
	if n != 0 {
		t.Fatalf("boundary should not be deleted, got %d", n)
	}

	if _, err := s.GetLink(1); err != nil {
		t.Fatalf("boundary link should still exist: %v", err)
	}
}
