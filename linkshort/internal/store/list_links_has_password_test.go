package store

import (
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestListLinksHasPasswordFilter(t *testing.T) {
	s := newTestStore(t)

	id1, err := s.CreateLinkEx("p1", "https://p1.com", "p1", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx p1: %v", err)
	}
	if err := s.SetLinkPassword(id1, "hash1"); err != nil {
		t.Fatalf("SetLinkPassword p1: %v", err)
	}
	id2, err := s.CreateLinkEx("p2", "https://p2.com", "p2", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx p2: %v", err)
	}
	if err := s.SetLinkPassword(id2, "hash2"); err != nil {
		t.Fatalf("SetLinkPassword p2: %v", err)
	}
	if err := s.UpdateLinkEx(id2, "p2", false, nil, nil, false, false); err != nil {
		t.Fatalf("UpdateLinkEx p2: %v", err)
	}
	if _, err := s.CreateLinkEx("o1", "https://o1.com", "o1", nil, nil, false, false); err != nil {
		t.Fatalf("CreateLinkEx o1: %v", err)
	}
	if _, err := s.CreateLinkEx("o2", "https://o2.com", "o2", nil, nil, false, false); err != nil {
		t.Fatalf("CreateLinkEx o2: %v", err)
	}

	getSlugs := func(links []*model.Link) []string {
		slugs := make([]string, 0, len(links))
		for _, l := range links {
			slugs = append(slugs, l.Slug)
		}
		return slugs
	}

	assertSetEqual := func(t *testing.T, expected, actual []string) {
		expMap := make(map[string]bool)
		for _, s := range expected {
			expMap[s] = true
		}
		if len(actual) != len(expMap) {
			t.Errorf("length mismatch: expected %d, got %d", len(expMap), len(actual))
		}
		for _, s := range actual {
			if !expMap[s] {
				t.Errorf("unexpected slug %q", s)
			}
			delete(expMap, s)
		}
		if len(expMap) > 0 {
			t.Errorf("missing slugs: %v", expMap)
		}
	}

	links, total, err := s.ListLinksFilteredEx3("", 1, 10, "", nil, nil, nil, nil)
	if err != nil {
		t.Fatalf("ListLinksFilteredEx3 all: %v", err)
	}
	if total != 4 {
		t.Errorf("all: total mismatch: expected 4, got %d", total)
	}
	assertSetEqual(t, []string{"p1", "p2", "o1", "o2"}, getSlugs(links))

	links, total, err = s.ListLinksFilteredEx3("", 1, 10, "", nil, nil, nil, boolPtr(true))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx3 has_password=true: %v", err)
	}
	if total != 2 {
		t.Errorf("has_password=true: total mismatch: expected 2, got %d", total)
	}
	assertSetEqual(t, []string{"p1", "p2"}, getSlugs(links))

	links, total, err = s.ListLinksFilteredEx3("", 1, 10, "", nil, nil, nil, boolPtr(false))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx3 has_password=false: %v", err)
	}
	if total != 2 {
		t.Errorf("has_password=false: total mismatch: expected 2, got %d", total)
	}
	assertSetEqual(t, []string{"o1", "o2"}, getSlugs(links))

	links, total, err = s.ListLinksFilteredEx3("", 1, 10, "", boolPtr(false), nil, nil, boolPtr(true))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx3 has_password=true enabled=false: %v", err)
	}
	if total != 1 {
		t.Errorf("has_password=true enabled=false: total mismatch: expected 1, got %d", total)
	}
	if len(links) != 1 {
		t.Errorf("has_password=true enabled=false: links length mismatch: expected 1, got %d", len(links))
	} else if links[0].Slug != "p2" {
		t.Errorf("has_password=true enabled=false: expected slug p2, got %q", links[0].Slug)
	}

	links, total, err = s.ListLinksFilteredEx3("o1", 1, 10, "", nil, nil, nil, boolPtr(false))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx3 has_password=false search=o1: %v", err)
	}
	if total != 1 {
		t.Errorf("has_password=false search=o1: total mismatch: expected 1, got %d", total)
	}
	if len(links) != 1 {
		t.Errorf("has_password=false search=o1: links length mismatch: expected 1, got %d", len(links))
	} else if links[0].Slug != "o1" {
		t.Errorf("has_password=false search=o1: expected slug o1, got %q", links[0].Slug)
	}

	page1, total, err := s.ListLinksFilteredEx3("", 1, 1, "", nil, nil, nil, boolPtr(true))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx3 page 1: %v", err)
	}
	if total != 2 {
		t.Errorf("pagination: total mismatch: expected 2, got %d", total)
	}
	if len(page1) != 1 {
		t.Fatalf("pagination: page 1 length mismatch: expected 1, got %d", len(page1))
	}
	page2, total, err := s.ListLinksFilteredEx3("", 2, 1, "", nil, nil, nil, boolPtr(true))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx3 page 2: %v", err)
	}
	if total != 2 {
		t.Errorf("pagination: total mismatch: expected 2, got %d", total)
	}
	if len(page2) != 1 {
		t.Fatalf("pagination: page 2 length mismatch: expected 1, got %d", len(page2))
	}
	if page1[0].Slug == page2[0].Slug {
		t.Errorf("pagination: pages overlap on slug %q", page1[0].Slug)
	}
}
