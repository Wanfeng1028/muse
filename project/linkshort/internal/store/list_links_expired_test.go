package store

import (
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestListLinksExpiredFilter(t *testing.T) {
	s := newTestStore(t)

	past := time.Now().Add(-time.Hour)
	future := time.Now().Add(time.Hour)

	_, err := s.CreateLinkEx("e1", "https://e1.com", "e1", &past, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx e1: %v", err)
	}
	id2, err := s.CreateLinkEx("e2", "https://e2.com", "e2", &past, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx e2: %v", err)
	}
	if err := s.UpdateLinkEx(id2, "e2", false, &past, nil, false, false); err != nil {
		t.Fatalf("UpdateLinkEx e2: %v", err)
	}
	_, err = s.CreateLinkEx("u1", "https://u1.com", "u1", &future, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx u1: %v", err)
	}
	_, err = s.CreateLinkEx("n1", "https://n1.com", "n1", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx n1: %v", err)
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

	links, total, err := s.ListLinksFilteredEx2("", 1, 10, "", nil, nil, nil)
	if err != nil {
		t.Fatalf("ListLinksFilteredEx2 all: %v", err)
	}
	if total != 4 {
		t.Errorf("all: total mismatch: expected 4, got %d", total)
	}
	if len(links) != 4 {
		t.Errorf("all: links length mismatch: expected 4, got %d", len(links))
	}
	assertSetEqual(t, []string{"e1", "e2", "u1", "n1"}, getSlugs(links))

	links, total, err = s.ListLinksFilteredEx2("", 1, 10, "", nil, nil, boolPtr(true))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx2 expired=true: %v", err)
	}
	if total != 2 {
		t.Errorf("expired=true: total mismatch: expected 2, got %d", total)
	}
	if len(links) != 2 {
		t.Errorf("expired=true: links length mismatch: expected 2, got %d", len(links))
	}
	assertSetEqual(t, []string{"e1", "e2"}, getSlugs(links))

	links, total, err = s.ListLinksFilteredEx2("", 1, 10, "", nil, nil, boolPtr(false))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx2 expired=false: %v", err)
	}
	if total != 2 {
		t.Errorf("expired=false: total mismatch: expected 2, got %d", total)
	}
	if len(links) != 2 {
		t.Errorf("expired=false: links length mismatch: expected 2, got %d", len(links))
	}
	assertSetEqual(t, []string{"u1", "n1"}, getSlugs(links))

	links, total, err = s.ListLinksFilteredEx2("", 1, 10, "", boolPtr(false), nil, boolPtr(true))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx2 expired=true enabled=false: %v", err)
	}
	if total != 1 {
		t.Errorf("expired=true enabled=false: total mismatch: expected 1, got %d", total)
	}
	if len(links) != 1 {
		t.Errorf("expired=true enabled=false: links length mismatch: expected 1, got %d", len(links))
	} else if links[0].Slug != "e2" {
		t.Errorf("expired=true enabled=false: expected slug e2, got %q", links[0].Slug)
	}

	links, total, err = s.ListLinksFilteredEx2("u1", 1, 10, "", nil, nil, boolPtr(false))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx2 expired=false search=u1: %v", err)
	}
	if total != 1 {
		t.Errorf("expired=false search=u1: total mismatch: expected 1, got %d", total)
	}
	if len(links) != 1 {
		t.Errorf("expired=false search=u1: links length mismatch: expected 1, got %d", len(links))
	} else if links[0].Slug != "u1" {
		t.Errorf("expired=false search=u1: expected slug u1, got %q", links[0].Slug)
	}

	page1, total, err := s.ListLinksFilteredEx2("", 1, 1, "", nil, nil, boolPtr(false))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx2 page 1: %v", err)
	}
	if total != 2 {
		t.Errorf("pagination: total mismatch: expected 2, got %d", total)
	}
	if len(page1) != 1 {
		t.Fatalf("pagination: page 1 length mismatch: expected 1, got %d", len(page1))
	}
	page2, total2, err := s.ListLinksFilteredEx2("", 2, 1, "", nil, nil, boolPtr(false))
	if err != nil {
		t.Fatalf("ListLinksFilteredEx2 page 2: %v", err)
	}
	if total2 != 2 {
		t.Errorf("pagination: page 2 total mismatch: expected 2, got %d", total2)
	}
	if len(page2) != 1 {
		t.Fatalf("pagination: page 2 length mismatch: expected 1, got %d", len(page2))
	}
	if page1[0].Slug == page2[0].Slug {
		t.Errorf("pagination: expected different slugs on page 1 and page 2, both got %q", page1[0].Slug)
	}
}
