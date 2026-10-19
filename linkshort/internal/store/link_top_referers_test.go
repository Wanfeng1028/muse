package store

import (
	"testing"
)

// TestLinkTopReferersEmpty 验证没有任何访问时返回空结果。
func TestLinkTopReferersEmpty(t *testing.T) {
	s := newTestStore(t)

	link, err := s.CreateLink("", "https://example.com/empty", "t", nil)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}

	stats, err := s.LinkTopReferers(link, 8)
	if err != nil {
		t.Fatalf("link top referers: %v", err)
	}
	if len(stats) != 0 {
		t.Fatalf("expected empty stats, got %d entries: %+v", len(stats), stats)
	}
}

// TestLinkTopReferersOrder 验证多个来源按点击数降序排列。
func TestLinkTopReferersOrder(t *testing.T) {
	s := newTestStore(t)

	link, err := s.CreateLink("", "https://example.com/order", "t", nil)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}

	// a.example 3 次，b.example 1 次。
	for i := 0; i < 3; i++ {
		if err := s.RecordVisit(link, "1.2.3.4", "ua-1", "a.example"); err != nil {
			t.Fatalf("record visit a: %v", err)
		}
	}
	if err := s.RecordVisit(link, "1.2.3.5", "ua-2", "b.example"); err != nil {
		t.Fatalf("record visit b: %v", err)
	}

	stats, err := s.LinkTopReferers(link, 8)
	if err != nil {
		t.Fatalf("link top referers: %v", err)
	}
	if len(stats) != 2 {
		t.Fatalf("expected 2 stats, got %d: %+v", len(stats), stats)
	}
	if stats[0].Name != "a.example" || stats[0].Clicks != 3 {
		t.Fatalf("expected first a.example=3, got %+v", stats[0])
	}
	if stats[1].Name != "b.example" || stats[1].Clicks != 1 {
		t.Fatalf("expected second b.example=1, got %+v", stats[1])
	}
}

// TestLinkTopReferersDirect 验证空 referer 被记为 (direct)。
func TestLinkTopReferersDirect(t *testing.T) {
	s := newTestStore(t)

	link, err := s.CreateLink("", "https://example.com/direct", "t", nil)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}

	if err := s.RecordVisit(link, "1.2.3.6", "ua-direct", ""); err != nil {
		t.Fatalf("record direct visit: %v", err)
	}
	if err := s.RecordVisit(link, "1.2.3.7", "ua-direct", ""); err != nil {
		t.Fatalf("record direct visit: %v", err)
	}

	stats, err := s.LinkTopReferers(link, 8)
	if err != nil {
		t.Fatalf("link top referers: %v", err)
	}
	if len(stats) != 1 {
		t.Fatalf("expected 1 stat, got %d: %+v", len(stats), stats)
	}
	if stats[0].Name != "(direct)" || stats[0].Clicks != 2 {
		t.Fatalf("expected (direct)=2, got %+v", stats[0])
	}
}

// TestLinkTopReferersIsolation 验证不同链接的来源统计互不影响。
func TestLinkTopReferersIsolation(t *testing.T) {
	s := newTestStore(t)

	linkA, err := s.CreateLink("", "https://example.com/a", "t", nil)
	if err != nil {
		t.Fatalf("create link a: %v", err)
	}
	linkB, err := s.CreateLink("", "https://example.com/b", "t", nil)
	if err != nil {
		t.Fatalf("create link b: %v", err)
	}

	if err := s.RecordVisit(linkA, "1.2.3.8", "ua-a", "a.example"); err != nil {
		t.Fatalf("record visit a: %v", err)
	}
	if err := s.RecordVisit(linkB, "1.2.3.9", "ua-b", "b.example"); err != nil {
		t.Fatalf("record visit b: %v", err)
	}

	statsA, err := s.LinkTopReferers(linkA, 8)
	if err != nil {
		t.Fatalf("link top referers a: %v", err)
	}
	if len(statsA) != 1 || statsA[0].Name != "a.example" || statsA[0].Clicks != 1 {
		t.Fatalf("expected link A only a.example=1, got %+v", statsA)
	}

	statsB, err := s.LinkTopReferers(linkB, 8)
	if err != nil {
		t.Fatalf("link top referers b: %v", err)
	}
	if len(statsB) != 1 || statsB[0].Name != "b.example" || statsB[0].Clicks != 1 {
		t.Fatalf("expected link B only b.example=1, got %+v", statsB)
	}
}
