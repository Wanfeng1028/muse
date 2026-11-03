package store

import (
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
)

func TestBackfillBurnedAtUsesLastVisit(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()
	s := New(database)

	now := time.Now().UTC().Truncate(time.Second)
	t1 := now.Add(-2 * time.Second)
	t2 := now.Add(-1 * time.Second)

	id, err := s.CreateLinkEx("slug1", "https://example.com", "title", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if err := s.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned: %v", err)
	}
	if _, err := database.Exec(`UPDATE links SET burned_at = NULL WHERE id = ?`, id); err != nil {
		t.Fatalf("clear burned_at: %v", err)
	}
	if _, err := database.Exec(`INSERT INTO visits (link_id, ts) VALUES (?, ?)`, id, formatTime(t1)); err != nil {
		t.Fatalf("insert visit t1: %v", err)
	}
	if _, err := database.Exec(`INSERT INTO visits (link_id, ts) VALUES (?, ?)`, id, formatTime(t2)); err != nil {
		t.Fatalf("insert visit t2: %v", err)
	}

	n, err := s.BackfillBurnedAt()
	if err != nil {
		t.Fatalf("BackfillBurnedAt: %v", err)
	}
	if n != 1 {
		t.Errorf("expected BackfillBurnedAt to return 1, got %d", n)
	}

	link, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if link.BurnedAt == nil {
		t.Fatalf("expected BurnedAt non-nil, got nil")
	}
	if !link.BurnedAt.Equal(t2) {
		t.Errorf("expected BurnedAt %v, got %v", t2, *link.BurnedAt)
	}

	// Idempotency: calling again should return 0
	n2, err := s.BackfillBurnedAt()
	if err != nil {
		t.Fatalf("BackfillBurnedAt idempotent: %v", err)
	}
	if n2 != 0 {
		t.Errorf("expected idempotent BackfillBurnedAt to return 0, got %d", n2)
	}
}

func TestBackfillBurnedAtFallsBackToUpdatedAt(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()
	s := New(database)

	id, err := s.CreateLinkEx("slug2", "https://example.com", "title", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if err := s.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned: %v", err)
	}
	if _, err := database.Exec(`UPDATE links SET burned_at = NULL WHERE id = ?`, id); err != nil {
		t.Fatalf("clear burned_at: %v", err)
	}

	n, err := s.BackfillBurnedAt()
	if err != nil {
		t.Fatalf("BackfillBurnedAt: %v", err)
	}
	if n != 1 {
		t.Errorf("expected BackfillBurnedAt to return 1, got %d", n)
	}

	link, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if link.BurnedAt == nil {
		t.Errorf("expected BurnedAt non-nil, got nil")
	}
}

func TestBackfillBurnedAtSkipsEnabledBurnLink(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()
	s := New(database)

	id, err := s.CreateLinkEx("slug3", "https://example.com", "title", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	// Do NOT call MarkBurned — link remains enabled

	n, err := s.BackfillBurnedAt()
	if err != nil {
		t.Fatalf("BackfillBurnedAt: %v", err)
	}
	if n != 0 {
		t.Errorf("expected BackfillBurnedAt to return 0, got %d", n)
	}

	link, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if link.BurnedAt != nil {
		t.Errorf("expected BurnedAt nil, got %v", *link.BurnedAt)
	}
}

func TestBackfillBurnedAtSkipsNonBurnLink(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()
	s := New(database)

	id, err := s.CreateLinkEx("slug4", "https://example.com", "title", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	if err := s.UpdateLinkEx(id, "title", false, nil, nil, false, false); err != nil {
		t.Fatalf("UpdateLinkEx: %v", err)
	}

	n, err := s.BackfillBurnedAt()
	if err != nil {
		t.Fatalf("BackfillBurnedAt: %v", err)
	}
	if n != 0 {
		t.Errorf("expected BackfillBurnedAt to return 0, got %d", n)
	}
}

func TestBackfillBurnedAtKeepsExistingAndIdempotent(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()
	s := New(database)

	id, err := s.CreateLinkEx("slug5", "https://example.com", "title", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if err := s.MarkBurned(id); err != nil {
		t.Fatalf("MarkBurned: %v", err)
	}

	// Do NOT clear burned_at — it already has a value

	linkBefore, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink before: %v", err)
	}
	if linkBefore.BurnedAt == nil {
		t.Fatalf("expected BurnedAt non-nil after MarkBurned, got nil")
	}
	existingBurnedAt := *linkBefore.BurnedAt

	n, err := s.BackfillBurnedAt()
	if err != nil {
		t.Fatalf("BackfillBurnedAt: %v", err)
	}
	if n != 0 {
		t.Errorf("expected BackfillBurnedAt to return 0, got %d", n)
	}

	linkAfter, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink after: %v", err)
	}
	if linkAfter.BurnedAt == nil {
		t.Fatalf("expected BurnedAt non-nil after backfill, got nil")
	}
	if !linkAfter.BurnedAt.Equal(existingBurnedAt) {
		t.Errorf("expected BurnedAt unchanged %v, got %v", existingBurnedAt, *linkAfter.BurnedAt)
	}
}
