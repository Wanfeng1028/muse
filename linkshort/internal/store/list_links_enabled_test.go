package store

import (
	"testing"
)

func boolPtr(b bool) *bool {
	return &b
}

func TestListLinksEnabledFilter(t *testing.T) {
	st := newTestStore(t)

	// Create 2 enabled links
	st.CreateLink("en1", "https://en1.com", "en1", nil)
	st.CreateLink("en2", "https://en2.com", "en2", nil)

	// Create 1 link then disable it
	dis1ID, err := st.CreateLink("dis1", "https://dis1.com", "dis1", nil)
	if err != nil {
		t.Fatalf("create dis1: %v", err)
	}
	err = st.UpdateLinkEx(dis1ID, "dis1", false, nil, nil, false, false)
	if err != nil {
		t.Fatalf("disable dis1: %v", err)
	}

	// ① enabled=nil → all 3 links, total=3
	links, total, err := st.ListLinksFiltered("", 1, 20, "created_at", nil)
	if err != nil {
		t.Fatalf("① err: %v", err)
	}
	if total != 3 {
		t.Errorf("① total=%d, want 3", total)
	}
	if len(links) != 3 {
		t.Errorf("① len=%d, want 3", len(links))
	}

	// ② enabled=true → only en1/en2, total=2
	links, total, err = st.ListLinksFiltered("", 1, 20, "created_at", boolPtr(true))
	if err != nil {
		t.Fatalf("② err: %v", err)
	}
	if total != 2 {
		t.Errorf("② total=%d, want 2", total)
	}
	if len(links) != 2 {
		t.Errorf("② len=%d, want 2", len(links))
	}

	// ③ enabled=false → only dis1, total=1
	links, total, err = st.ListLinksFiltered("", 1, 20, "created_at", boolPtr(false))
	if err != nil {
		t.Fatalf("③ err: %v", err)
	}
	if total != 1 {
		t.Errorf("③ total=%d, want 1", total)
	}
	if len(links) != 1 {
		t.Errorf("③ len=%d, want 1", len(links))
	}
	if len(links) > 0 && links[0].Slug != "dis1" {
		t.Errorf("③ slug=%s, want dis1", links[0].Slug)
	}

	// ④ enabled=false, search="dis1" → only dis1, total=1
	links, total, err = st.ListLinksFiltered("dis1", 1, 20, "created_at", boolPtr(false))
	if err != nil {
		t.Fatalf("④ err: %v", err)
	}
	if total != 1 {
		t.Errorf("④ total=%d, want 1", total)
	}
	if len(links) != 1 {
		t.Errorf("④ len=%d, want 1", len(links))
	}
	if len(links) > 0 && links[0].Slug != "dis1" {
		t.Errorf("④ slug=%s, want dis1", links[0].Slug)
	}

	// Create 4 more enabled links for pagination
	st.CreateLink("pg1", "https://pg1.com", "pg1", nil)
	st.CreateLink("pg2", "https://pg2.com", "pg2", nil)
	st.CreateLink("pg3", "https://pg3.com", "pg3", nil)
	st.CreateLink("pg4", "https://pg4.com", "pg4", nil)

	// ⑤ enabled=true, perPage=3: page1=3, page2=3, no overlap, total=6
	links1, total, err := st.ListLinksFiltered("", 1, 3, "created_at", boolPtr(true))
	if err != nil {
		t.Fatalf("⑤ page1 err: %v", err)
	}
	if total != 6 {
		t.Errorf("⑤ total=%d, want 6", total)
	}
	if len(links1) != 3 {
		t.Errorf("⑤ page1 len=%d, want 3", len(links1))
	}

	links2, total2, err := st.ListLinksFiltered("", 2, 3, "created_at", boolPtr(true))
	if err != nil {
		t.Fatalf("⑤ page2 err: %v", err)
	}
	if total2 != 6 {
		t.Errorf("⑤ page2 total=%d, want 6", total2)
	}
	if len(links2) != 3 {
		t.Errorf("⑤ page2 len=%d, want 3", len(links2))
	}

	// No overlap between pages
	seen := make(map[string]bool)
	for _, l := range links1 {
		seen[l.Slug] = true
	}
	for _, l := range links2 {
		if seen[l.Slug] {
			t.Errorf("⑤ overlap slug=%s between page1 and page2", l.Slug)
		}
	}
}
