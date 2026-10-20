package store

// 深测补强：访问画像聚合边界（时段分布/地域分布）。编排手工编写（模型输出碎片化，弃用）。

import (
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
)

func newGeoTestStore(t *testing.T) *Store {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open 失败: %v", err)
	}
	t.Cleanup(func() { _ = database.Close() })
	return New(database)
}

func mustCreateGeoLink(t *testing.T, s *Store, slug string) int64 {
	t.Helper()
	id, err := s.CreateLinkEx(slug, "https://example.com/"+slug, "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx 失败: %v", err)
	}
	return id
}

func TestHourlyStats_空库全零(t *testing.T) {
	s := newGeoTestStore(t)
	hs, err := s.HourlyStats(0, 7)
	if err != nil {
		t.Fatalf("HourlyStats 失败: %v", err)
	}
	if hs.Total != 0 {
		t.Errorf("期望 Total==0，实际 %d", hs.Total)
	}
	if len(hs.Hours) != 24 || len(hs.Weekdays) != 7 {
		t.Fatalf("期望 Hours 24 / Weekdays 7，实际 %d/%d", len(hs.Hours), len(hs.Weekdays))
	}
	for i, v := range hs.Hours {
		if v != 0 {
			t.Errorf("Hours[%d] 期望 0，实际 %d", i, v)
		}
	}
	for i, v := range hs.Weekdays {
		if v != 0 {
			t.Errorf("Weekdays[%d] 期望 0，实际 %d", i, v)
		}
	}
}

func TestHourlyStats_当前小时聚合(t *testing.T) {
	s := newGeoTestStore(t)
	id := mustCreateGeoLink(t, s, "h1")
	for i := 0; i < 5; i++ {
		if err := s.RecordVisitNoCount(id, "hash", "ua", "", "", "", "", ""); err != nil {
			t.Fatalf("RecordVisitNoCount 失败: %v", err)
		}
	}
	hs, err := s.HourlyStats(id, 1)
	if err != nil {
		t.Fatalf("HourlyStats 失败: %v", err)
	}
	if hs.Total != 5 {
		t.Errorf("期望 Total==5，实际 %d", hs.Total)
	}
	now := time.Now().UTC()
	if hs.Hours[now.Hour()] != 5 {
		t.Errorf("期望 Hours[%d]==5，实际 %d", now.Hour(), hs.Hours[now.Hour()])
	}
	if hs.Weekdays[int(now.Weekday())] != 5 {
		t.Errorf("期望 Weekdays[%d]==5，实际 %d", int(now.Weekday()), hs.Weekdays[int(now.Weekday())])
	}
	sum := int64(0)
	for _, v := range hs.Hours {
		sum += v
	}
	if sum != 5 {
		t.Errorf("24 小时总和期望 5，实际 %d", sum)
	}
}

func TestHourlyStats_全局与单链(t *testing.T) {
	s := newGeoTestStore(t)
	id1 := mustCreateGeoLink(t, s, "g1")
	id2 := mustCreateGeoLink(t, s, "g2")
	for i := 0; i < 5; i++ {
		if err := s.RecordVisitNoCount(id1, "h", "u", "", "", "", "", ""); err != nil {
			t.Fatalf("RecordVisitNoCount 失败: %v", err)
		}
	}
	for i := 0; i < 3; i++ {
		if err := s.RecordVisitNoCount(id2, "h", "u", "", "", "", "", ""); err != nil {
			t.Fatalf("RecordVisitNoCount 失败: %v", err)
		}
	}
	all, err := s.HourlyStats(0, 1)
	if err != nil {
		t.Fatalf("HourlyStats 全局失败: %v", err)
	}
	if all.Total != 8 {
		t.Errorf("全局期望 Total==8，实际 %d", all.Total)
	}
	one, err := s.HourlyStats(id1, 1)
	if err != nil {
		t.Fatalf("HourlyStats 单链失败: %v", err)
	}
	if one.Total != 5 {
		t.Errorf("单链期望 Total==5，实际 %d", one.Total)
	}
	if one.LinkID != id1 {
		t.Errorf("期望 LinkID==%d，实际 %d", id1, one.LinkID)
	}
}

func TestGeoStats_全未知占比(t *testing.T) {
	s := newGeoTestStore(t)
	id := mustCreateGeoLink(t, s, "u1")
	for i := 0; i < 4; i++ {
		if err := s.RecordVisitNoCount(id, "h", "u", "", "", "", "", ""); err != nil {
			t.Fatalf("RecordVisitNoCount 失败: %v", err)
		}
	}
	ov, err := s.GeoStats(id, 7, "", 8)
	if err != nil {
		t.Fatalf("GeoStats 失败: %v", err)
	}
	if ov.TotalClicks != 4 {
		t.Errorf("期望 TotalClicks==4，实际 %d", ov.TotalClicks)
	}
	if ov.UnknownPct != 100.0 {
		t.Errorf("全未知期望 UnknownPct==100.0（百分制），实际 %v", ov.UnknownPct)
	}
	if len(ov.Items) != 0 {
		t.Errorf("全未知期望 Items 为空，实际 %d 条", len(ov.Items))
	}
}

func TestGeoStats_国家聚合与下钻(t *testing.T) {
	s := newGeoTestStore(t)
	id := mustCreateGeoLink(t, s, "c1")
	for i := 0; i < 3; i++ {
		if err := s.RecordVisitNoCount(id, "h1", "u", "", "CN", "中国", "广东", "深圳"); err != nil {
			t.Fatalf("RecordVisitNoCount 失败: %v", err)
		}
	}
	for i := 0; i < 2; i++ {
		if err := s.RecordVisitNoCount(id, "h2", "u", "", "US", "美国", "", ""); err != nil {
			t.Fatalf("RecordVisitNoCount 失败: %v", err)
		}
	}
	ov, err := s.GeoStats(0, 7, "", 8)
	if err != nil {
		t.Fatalf("GeoStats 失败: %v", err)
	}
	if ov.TotalClicks != 5 {
		t.Errorf("期望 TotalClicks==5，实际 %d", ov.TotalClicks)
	}
	if len(ov.Items) != 2 {
		t.Fatalf("期望 2 个国家，实际 %d", len(ov.Items))
	}
	// 按 clicks 降序：CN 在前
	if ov.Items[0].CountryCode != "CN" || ov.Items[0].Clicks != 3 {
		t.Errorf("期望首项 CN/3，实际 %s/%d", ov.Items[0].CountryCode, ov.Items[0].Clicks)
	}
	// country 下钻只统计该国家
	us, err := s.GeoStats(0, 7, "US", 8)
	if err != nil {
		t.Fatalf("GeoStats 下钻失败: %v", err)
	}
	if us.TotalClicks != 2 {
		t.Errorf("下钻 US 期望 TotalClicks==2，实际 %d", us.TotalClicks)
	}
	if len(us.Items) != 1 || us.Items[0].CountryCode != "US" {
		t.Errorf("下钻 US 期望 1 项 US，实际 %d 项", len(us.Items))
	}
	// 不存在的国家下钻为空且不崩
	xx, err := s.GeoStats(0, 7, "XX", 8)
	if err != nil {
		t.Fatalf("GeoStats 下钻 XX 失败: %v", err)
	}
	if len(xx.Items) != 0 {
		t.Errorf("下钻 XX 期望 Items 为空，实际 %d 项", len(xx.Items))
	}
	if xx.TotalClicks != 0 {
		t.Errorf("下钻 XX 期望 TotalClicks==0，实际 %d", xx.TotalClicks)
	}
}
