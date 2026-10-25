package store

import (
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestListLinksBurnFilter(t *testing.T) {
	s := newTestStore(t)

	// create b1 (burn true, enabled default true)
	_, err := s.CreateLinkEx("b1", "https://b1.com", "b1", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx b1: %v", err)
	}

	// create b2 (burn true) then disable it
	id2, err := s.CreateLinkEx("b2", "https://b2.com", "b2", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx b2: %v", err)
	}
	if err := s.UpdateLinkEx(id2, "b2", false, nil, nil, true, false); err != nil {
		t.Fatalf("UpdateLinkEx b2: %v", err)
	}

	// create n1 (burn false)
	_, err = s.CreateLinkEx("n1", "https://n1.com", "n1", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx n1: %v", err)
	}

	// create n2 (burn false) then disable it
	id4, err := s.CreateLinkEx("n2", "https://n2.com", "n2", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx n2: %v", err)
	}
	if err := s.UpdateLinkEx(id4, "n2", false, nil, nil, false, false); err != nil {
		t.Fatalf("UpdateLinkEx n2: %v", err)
	}

	// helper to extract slugs
	getSlugs := func(links []*model.Link) []string {
		slugs := make([]string, 0, len(links))
		for _, l := range links {
			slugs = append(slugs, l.Slug)
		}
		return slugs
	}

	// helper to compare unordered string slices
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

	// 1. burn=nil, enabled=nil => all four links
	{
		links, total, err := s.ListLinksFilteredEx("", 1, 100, "", nil, nil)
		if err != nil {
			t.Fatalf("ListLinksFilteredEx (all): %v", err)
		}
		if total != 4 {
			t.Errorf("total expected 4, got %d", total)
		}
		if len(links) != 4 {
			t.Errorf("len expected 4, got %d", len(links))
		}
		slugs := getSlugs(links)
		assertSetEqual(t, []string{"b1", "b2", "n1", "n2"}, slugs)
	}

	// 2. burn=true => b1 and b2
	{
		burnTrue := boolPtr(true)
		links, total, err := s.ListLinksFilteredEx("", 1, 100, "", nil, burnTrue)
		if err != nil {
			t.Fatalf("ListLinksFilteredEx (burn=true): %v", err)
		}
		if total != 2 {
			t.Errorf("total expected 2, got %d", total)
		}
		if len(links) != 2 {
			t.Errorf("len expected 2, got %d", len(links))
		}
		slugs := getSlugs(links)
		assertSetEqual(t, []string{"b1", "b2"}, slugs)
	}

	// 3. burn=false => n1 and n2
	{
		burnFalse := boolPtr(false)
		links, total, err := s.ListLinksFilteredEx("", 1, 100, "", nil, burnFalse)
		if err != nil {
			t.Fatalf("ListLinksFilteredEx (burn=false): %v", err)
		}
		if total != 2 {
			t.Errorf("total expected 2, got %d", total)
		}
		if len(links) != 2 {
			t.Errorf("len expected 2, got %d", len(links))
		}
		slugs := getSlugs(links)
		assertSetEqual(t, []string{"n1", "n2"}, slugs)
	}

	// 4. burn=true, enabled=true => only b1
	{
		burnTrue := boolPtr(true)
		enabledTrue := boolPtr(true)
		links, total, err := s.ListLinksFilteredEx("", 1, 100, "", enabledTrue, burnTrue)
		if err != nil {
			t.Fatalf("ListLinksFilteredEx (burn=true, enabled=true): %v", err)
		}
		if total != 1 {
			t.Errorf("total expected 1, got %d", total)
		}
		if len(links) != 1 {
			t.Errorf("len expected 1, got %d", len(links))
		}
		if links[0].Slug != "b1" {
			t.Errorf("expected slug b1, got %s", links[0].Slug)
		}
	}

	// 5. burn=true, enabled=false => only b2
	{
		burnTrue := boolPtr(true)
		enabledFalse := boolPtr(false)
		links, total, err := s.ListLinksFilteredEx("", 1, 100, "", enabledFalse, burnTrue)
		if err != nil {
			t.Fatalf("ListLinksFilteredEx (burn=true, enabled=false): %v", err)
		}
		if total != 1 {
			t.Errorf("total expected 1, got %d", total)
		}
		if len(links) != 1 {
			t.Errorf("len expected 1, got %d", len(links))
		}
		if links[0].Slug != "b2" {
			t.Errorf("expected slug b2, got %s", links[0].Slug)
		}
	}

	// 6. burn=false, search="n1" => only n1
	{
		burnFalse := boolPtr(false)
		links, total, err := s.ListLinksFilteredEx("n1", 1, 100, "", nil, burnFalse)
		if err != nil {
			t.Fatalf("ListLinksFilteredEx (search=n1): %v", err)
		}
		if total != 1 {
			t.Errorf("total expected 1, got %d", total)
		}
		if len(links) != 1 {
			t.Errorf("len expected 1, got %d", len(links))
		}
		if links[0].Slug != "n1" {
			t.Errorf("expected slug n1, got %s", links[0].Slug)
		}
	}

	// 7. burn=true pagination
	{
		burnTrue := boolPtr(true)
		// page 1, perPage 1
		page1Links, total, err := s.ListLinksFilteredEx("", 1, 1, "", nil, burnTrue)
		if err != nil {
			t.Fatalf("ListLinksFilteredEx (page1): %v", err)
		}
		if total != 2 {
			t.Errorf("total expected 2, got %d", total)
		}
		if len(page1Links) != 1 {
			t.Errorf("page1 len expected 1, got %d", len(page1Links))
		}
		slugPage1 := page1Links[0].Slug

		// page 2, perPage 1
		page2Links, total2, err := s.ListLinksFilteredEx("", 2, 1, "", nil, burnTrue)
		if err != nil {
			t.Fatalf("ListLinksFilteredEx (page2): %v", err)
		}
		if total2 != 2 {
			t.Errorf("total2 expected 2, got %d", total2)
		}
		if len(page2Links) != 1 {
			t.Errorf("page2 len expected 1, got %d", len(page2Links))
		}
		slugPage2 := page2Links[0].Slug

		if slugPage2 == slugPage1 {
			t.Errorf("page2 slug should differ from page1, both %s", slugPage1)
		}
	}
}
