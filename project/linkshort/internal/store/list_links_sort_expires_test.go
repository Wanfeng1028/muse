package store

import (
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestListLinksSortByExpiresAt(t *testing.T) {
	s := newTestStore(t)

	far := time.Now().Add(2 * time.Hour)
	near := time.Now().Add(time.Hour)
	past := time.Now().Add(-time.Hour)

	if _, err := s.CreateLinkEx("far", "https://far.com", "far", &far, nil, false, false); err != nil {
		t.Fatalf("CreateLinkEx far: %v", err)
	}
	if _, err := s.CreateLinkEx("never", "https://never.com", "never", nil, nil, false, false); err != nil {
		t.Fatalf("CreateLinkEx never: %v", err)
	}
	if _, err := s.CreateLinkEx("past", "https://past.com", "past", &past, nil, false, false); err != nil {
		t.Fatalf("CreateLinkEx past: %v", err)
	}
	if _, err := s.CreateLinkEx("near", "https://near.com", "near", &near, nil, false, false); err != nil {
		t.Fatalf("CreateLinkEx near: %v", err)
	}

	getSlugs := func(links []*model.Link) []string {
		slugs := make([]string, 0, len(links))
		for _, l := range links {
			slugs = append(slugs, l.Slug)
		}
		return slugs
	}

	links, total, err := s.ListLinksFilteredEx3("", 1, 10, "expires_at", nil, nil, nil, nil)
	if err != nil {
		t.Fatalf("ListLinksFilteredEx3 expires_at: %v", err)
	}
	if total != 4 {
		t.Fatalf("total mismatch: expected 4, got %d", total)
	}
	want := []string{"far", "near", "past", "never"}
	got := getSlugs(links)
	if len(got) != len(want) {
		t.Fatalf("order length mismatch: expected %v, got %v", want, got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("order mismatch at %d: expected %v, got %v", i, want, got)
		}
	}

	// Invalid sort falls back to created_at (newest first is not asserted here,
	// only that the call succeeds and returns all rows).
	links, total, err = s.ListLinksFilteredEx3("", 1, 10, "bogus", nil, nil, nil, nil)
	if err != nil {
		t.Fatalf("ListLinksFilteredEx3 bogus: %v", err)
	}
	if total != 4 || len(links) != 4 {
		t.Fatalf("bogus sort: expected 4 rows, got total=%d len=%d", total, len(links))
	}
}
