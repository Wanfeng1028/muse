// internal/store/geo_v19_test.go
package store

import (
	"testing"
	"time"
)

func TestGeoUVDedup(t *testing.T) {
	s, id1, _ := newGeoStore(t)

	for i := 0; i < 3; i++ {
		if err := s.RecordVisitGeo(id1, "hash-dup", "ua-a", "", "CN", "China", "Guangdong", "Guangzhou"); err != nil {
			t.Fatalf("RecordVisitGeo: %v", err)
		}
	}

	ov, err := s.GeoStats(0, 0, "", 10)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if len(ov.Items) != 1 {
		t.Fatalf("want 1 item, got %d", len(ov.Items))
	}
	it := ov.Items[0]
	if it.Clicks != 3 {
		t.Fatalf("want Clicks 3, got %d", it.Clicks)
	}
	if it.UV != 1 {
		t.Fatalf("want UV 1, got %d", it.UV)
	}
	if ov.TotalUV != 1 {
		t.Fatalf("want TotalUV 1, got %d", ov.TotalUV)
	}
}

func TestGeoUVIgnoresEmptyIPHash(t *testing.T) {
	s, id1, _ := newGeoStore(t)

	if err := s.RecordVisitGeo(id1, "", "ua-x", "", "CN", "China", "Guangdong", "Guangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo empty 1: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "", "ua-y", "", "CN", "China", "Guangdong", "Guangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo empty 2: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "hash-real", "ua-z", "", "CN", "China", "Guangdong", "Guangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo real: %v", err)
	}

	ov, err := s.GeoStats(0, 0, "", 10)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if len(ov.Items) != 1 {
		t.Fatalf("want 1 item, got %d", len(ov.Items))
	}
	if ov.Items[0].UV != 1 {
		t.Fatalf("want UV 1 (empty hash not counted), got %d", ov.Items[0].UV)
	}
	if ov.TotalUV != 1 {
		t.Fatalf("want TotalUV 1, got %d", ov.TotalUV)
	}
	if ov.Items[0].Clicks != 3 {
		t.Fatalf("want Clicks 3, got %d", ov.Items[0].Clicks)
	}
}

func TestGeoDaysFilter(t *testing.T) {
	s, id1, _ := newGeoStore(t)

	old := nowUTC().AddDate(0, 0, -40).Format(time.RFC3339)
	if _, err := s.db.Exec(
		`INSERT INTO visits (link_id, ts, ip_hash, ua, referer, country_code, country_name, province, city)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		id1, old, "hash-old", "ua-old", "", "CN", "China", "Guangdong", "Guangzhou",
	); err != nil {
		t.Fatalf("insert old visit: %v", err)
	}

	if err := s.RecordVisitGeo(id1, "hash-new", "ua-new", "", "CN", "China", "Guangdong", "Guangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}

	ov30, err := s.GeoStats(0, 30, "", 10)
	if err != nil {
		t.Fatalf("GeoStats 30: %v", err)
	}
	if ov30.TotalClicks != 1 {
		t.Fatalf("want TotalClicks 1 (40d ago filtered), got %d", ov30.TotalClicks)
	}

	ovAll, err := s.GeoStats(0, 0, "", 10)
	if err != nil {
		t.Fatalf("GeoStats 0: %v", err)
	}
	if ovAll.TotalClicks != 2 {
		t.Fatalf("want TotalClicks 2 (days=0 no limit), got %d", ovAll.TotalClicks)
	}
}

func TestGeoCountryFilter(t *testing.T) {
	s, id1, _ := newGeoStore(t)

	if err := s.RecordVisitGeo(id1, "h-cn-1", "ua", "", "CN", "China", "Guangdong", "Guangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo CN 1: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "h-cn-2", "ua", "", "CN", "China", "Guangdong", "Shenzhen"); err != nil {
		t.Fatalf("RecordVisitGeo CN 2: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "h-us-1", "ua", "", "US", "United States", "California", "San Francisco"); err != nil {
		t.Fatalf("RecordVisitGeo US: %v", err)
	}

	ovCN, err := s.GeoStats(0, 0, "CN", 10)
	if err != nil {
		t.Fatalf("GeoStats CN: %v", err)
	}
	if ovCN.TotalClicks != 2 {
		t.Fatalf("want TotalClicks 2 for CN, got %d", ovCN.TotalClicks)
	}
	if len(ovCN.Items) == 0 {
		t.Fatalf("want non-empty items for CN")
	}
	for i, it := range ovCN.Items {
		if it.CountryCode != "CN" {
			t.Fatalf("item %d country_code = %q, want CN", i, it.CountryCode)
		}
	}

	ovXX, err := s.GeoStats(0, 0, "XX", 10)
	if err != nil {
		t.Fatalf("GeoStats XX: %v", err)
	}
	if ovXX.TotalClicks != 0 {
		t.Fatalf("want TotalClicks 0 for XX, got %d", ovXX.TotalClicks)
	}
	if ovXX.Items == nil {
		t.Fatalf("want non-nil empty Items, got nil")
	}
	if len(ovXX.Items) != 0 {
		t.Fatalf("want 0 items for XX, got %d", len(ovXX.Items))
	}
}

func TestGeoCityGrouping(t *testing.T) {
	s, id1, _ := newGeoStore(t)

	if err := s.RecordVisitGeo(id1, "h-gz-1", "ua", "", "CN", "China", "Guangdong", "Guangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo GZ 1: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "h-gz-2", "ua", "", "CN", "China", "Guangdong", "Guangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo GZ 2: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "h-sz-1", "ua", "", "CN", "China", "Guangdong", "Shenzhen"); err != nil {
		t.Fatalf("RecordVisitGeo SZ: %v", err)
	}

	ov, err := s.GeoStats(0, 0, "", 10)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if len(ov.Items) != 2 {
		t.Fatalf("want 2 city groups, got %d", len(ov.Items))
	}
	first := ov.Items[0]
	if first.City != "广州" && first.City != "Guangzhou" {
		t.Fatalf("want first City 广州/Guangzhou, got %q", first.City)
	}
	if first.Clicks != 2 {
		t.Fatalf("want first Clicks 2, got %d", first.Clicks)
	}
}

func TestGeoTotalsAndUnknownPct(t *testing.T) {
	s, id1, _ := newGeoStore(t)

	if err := s.RecordVisitGeo(id1, "h-cn-1", "ua", "", "CN", "China", "Guangdong", "Guangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo CN 1: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "h-cn-2", "ua", "", "CN", "China", "Guangdong", "Guangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo CN 2: %v", err)
	}
	if err := s.RecordVisitGeo(id1, "h-unk", "ua", "", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo unknown: %v", err)
	}

	ov, err := s.GeoStats(0, 0, "", 10)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if ov.TotalClicks != 3 {
		t.Fatalf("want TotalClicks 3, got %d", ov.TotalClicks)
	}
	if diff := ov.UnknownPct - 33.33; diff > 0.01 || diff < -0.01 {
		t.Fatalf("want UnknownPct≈33.33, got %v", ov.UnknownPct)
	}
	if len(ov.Items) != 1 {
		t.Fatalf("want 1 item (unknown excluded), got %d", len(ov.Items))
	}
}
