package store

import (
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
)

func newGeoStore(t *testing.T) (*Store, int64, int64) {
	t.Helper()
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	s := New(d)
	id1, err := s.CreateLink("geo-a", "https://example.com/a", "", nil)
	if err != nil {
		t.Fatalf("CreateLink geo-a: %v", err)
	}
	id2, err := s.CreateLink("geo-b", "https://example.com/b", "", nil)
	if err != nil {
		t.Fatalf("CreateLink geo-b: %v", err)
	}
	return s, id1, id2
}

func TestGeoStatsGrouping(t *testing.T) {
	s, id1, _ := newGeoStore(t)
	if err := s.RecordVisitGeo(id1, "h1", "ua", "ref", "CN", "中国", "广东", "广州"); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "h2", "ua", "ref", "CN", "中国", "广东", "广州"); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "h3", "ua", "ref", "US", "美国", "加州", "洛杉矶"); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "h4", "ua", "ref", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	ov, err := s.GeoStats(0, 0, "", 10)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if len(ov.Items) != 2 {
		t.Fatalf("want 2 groups, got %d: %+v", len(ov.Items), ov.Items)
	}
	if ov.Items[0].CountryCode != "CN" || ov.Items[0].Province != "广东" || ov.Items[0].Clicks != 2 {
		t.Fatalf("unexpected first group: %+v", ov.Items[0])
	}
	if ov.Items[1].CountryCode != "US" || ov.Items[1].Province != "加州" || ov.Items[1].Clicks != 1 {
		t.Fatalf("unexpected second group: %+v", ov.Items[1])
	}
}

func TestGeoStatsLinkFilter(t *testing.T) {
	s, id1, id2 := newGeoStore(t)
	if err := s.RecordVisitGeo(id1, "h1", "ua", "ref", "CN", "中国", "广东", "广州"); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	if err := s.RecordVisitGeo(id2, "h2", "ua", "ref", "US", "美国", "加州", "洛杉矶"); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	if err := s.RecordVisitGeo(id2, "h3", "ua", "ref", "US", "美国", "加州", "洛杉矶"); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	ov, err := s.GeoStats(id2, 0, "", 10)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if len(ov.Items) != 1 {
		t.Fatalf("want 1 group, got %d", len(ov.Items))
	}
	if ov.Items[0].CountryCode != "US" || ov.Items[0].Clicks != 2 {
		t.Fatalf("unexpected: %+v", ov.Items[0])
	}
}

func TestGeoStatsUnknownPct(t *testing.T) {
	s, id1, _ := newGeoStore(t)
	if err := s.RecordVisitGeo(id1, "h1", "ua", "ref", "CN", "中国", "广东", "广州"); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "h2", "ua", "ref", "US", "美国", "加州", "洛杉矶"); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "h3", "ua", "ref", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	ov, err := s.GeoStats(0, 0, "", 10)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	diff := ov.UnknownPct - 33.33
	if diff < -0.01 || diff > 0.01 {
		t.Fatalf("want ~33.33, got %v", ov.UnknownPct)
	}
}

func TestGeoStatsEmpty(t *testing.T) {
	s, _, _ := newGeoStore(t)
	ov, err := s.GeoStats(0, 0, "", 10)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if ov.Items == nil {
		t.Fatalf("items must be non-nil")
	}
	if len(ov.Items) != 0 {
		t.Fatalf("want 0 items, got %d", len(ov.Items))
	}
	if ov.UnknownPct != 0 {
		t.Fatalf("want 0 pct, got %v", ov.UnknownPct)
	}
}

func TestGeoStatsLimit(t *testing.T) {
	s, id1, _ := newGeoStore(t)
	codes := []string{"CN", "US", "JP", "DE", "FR"}
	for i, c := range codes {
		if err := s.RecordVisitGeo(id1, "h", "ua", "ref", c, c, "p", ""); err != nil {
			t.Fatalf("RecordVisitGeo %d: %v", i, err)
		}
	}
	ov, err := s.GeoStats(0, 0, "", 2)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if len(ov.Items) != 2 {
		t.Fatalf("want 2 items, got %d", len(ov.Items))
	}
}

func TestRecordVisitLegacyUnknown(t *testing.T) {
	s, id1, _ := newGeoStore(t)
	if err := s.RecordVisit(id1, "h1", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit: %v", err)
	}
	ov, err := s.GeoStats(0, 0, "", 10)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if len(ov.Items) != 0 {
		t.Fatalf("want 0 groups, got %d", len(ov.Items))
	}
	if ov.UnknownPct != 100 {
		t.Fatalf("want 100 pct, got %v", ov.UnknownPct)
	}
}
