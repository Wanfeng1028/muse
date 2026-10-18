package store

import (
	"bytes"
	"errors"
	"path/filepath"
	"strings"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	dbpkg "github.com/Wanfeng1028/muse/linkshort/internal/db"
)

func newDeep3Store(t *testing.T) *Store {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "deep3.db")
	db, err := dbpkg.Open(dbPath)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return New(db)
}

func deep3Create(t *testing.T, s *Store, slug, url string) int64 {
	t.Helper()
	id, err := s.CreateLinkEx(slug, url, "t", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx(%q,%q): %v", slug, url, err)
	}
	return id
}

func TestGetLinkNotFoundDeep3(t *testing.T) {
	s := newDeep3Store(t)
	_, err := s.GetLink(999999)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetLink missing err = %v, want ErrNotFound", err)
	}
}

func TestGetLinkBySlugNotFoundDeep3(t *testing.T) {
	s := newDeep3Store(t)
	_, err := s.GetLinkBySlug("no-such-slug")
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetLinkBySlug missing err = %v, want ErrNotFound", err)
	}
}

func TestUpdateLinkExNotFoundDeep3(t *testing.T) {
	s := newDeep3Store(t)
	err := s.UpdateLinkEx(424242, "t", true, nil, nil, false, false)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("UpdateLinkEx missing err = %v, want ErrNotFound", err)
	}
}

func TestUpdateLinkClearsMaxVisitsDeep3(t *testing.T) {
	s := newDeep3Store(t)
	max := int64(9)
	id, err := s.CreateLinkEx("clearmax", "https://example.com", "t", nil, &max, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if err := s.UpdateLinkEx(id, "t2", true, nil, nil, false, false); err != nil {
		t.Fatalf("UpdateLinkEx: %v", err)
	}
	got, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if got.MaxVisits != nil {
		t.Fatalf("MaxVisits = %v, want nil after clear", *got.MaxVisits)
	}
	if got.Title != "t2" {
		t.Fatalf("Title = %q, want t2", got.Title)
	}
}

func TestMarkBurnedNonBurnDeep3(t *testing.T) {
	s := newDeep3Store(t)
	id := deep3Create(t, s, "nb-burn", "https://example.com")
	if err := s.MarkBurned(id); !errors.Is(err, ErrNotFound) {
		t.Fatalf("MarkBurned on non-burn err = %v, want ErrNotFound", err)
	}
	got, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if !got.Enabled {
		t.Fatalf("non-burn link should stay enabled")
	}
}

func TestMarkBurnedMissingDeep3(t *testing.T) {
	s := newDeep3Store(t)
	if err := s.MarkBurned(777777); !errors.Is(err, ErrNotFound) {
		t.Fatalf("MarkBurned missing err = %v, want ErrNotFound", err)
	}
}

func TestMarkBurnedTwiceDeep3(t *testing.T) {
	s := newDeep3Store(t)
	id, err := s.CreateLinkEx("twiceburn", "https://example.com", "t", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if err := s.MarkBurned(id); err != nil {
		t.Fatalf("first MarkBurned: %v", err)
	}
	// 第二次仍能命中 burn=1 的行，RowsAffected 为 1，不报错。
	if err := s.MarkBurned(id); err != nil {
		t.Fatalf("second MarkBurned: %v", err)
	}
}

func TestPurgeLinkNotFoundDeep3(t *testing.T) {
	s := newDeep3Store(t)
	if err := s.PurgeLink(123123); !errors.Is(err, ErrNotFound) {
		t.Fatalf("PurgeLink missing err = %v, want ErrNotFound", err)
	}
}

func TestDeleteLinkNotFoundDeep3(t *testing.T) {
	s := newDeep3Store(t)
	if err := s.DeleteLink(321321); !errors.Is(err, ErrNotFound) {
		t.Fatalf("DeleteLink missing err = %v, want ErrNotFound", err)
	}
}

func TestPurgeExpiredBurnedNullBurnedAtDeep3(t *testing.T) {
	s := newDeep3Store(t)
	// burn=1 但 burned_at 为 NULL，应不在清理范围内。
	id, err := s.CreateLinkEx("nullburned", "https://example.com", "t", nil, nil, true, true)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if _, err := s.db.Exec(`UPDATE links SET burned_at=NULL WHERE id=?`, id); err != nil {
		t.Fatalf("set burned_at null: %v", err)
	}
	n, err := s.PurgeExpiredBurned(time.Now().UTC().Add(time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != 0 {
		t.Fatalf("PurgeExpiredBurned deleted %d, want 0", n)
	}
	if _, err := s.GetLink(id); err != nil {
		t.Fatalf("link with NULL burned_at should remain, err = %v", err)
	}
}

func TestPurgeExpiredBurnedExactBoundaryDeep3(t *testing.T) {
	s := newDeep3Store(t)
	id, err := s.CreateLinkEx("boundburn", "https://example.com", "t", nil, nil, true, true)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	exact := time.Now().UTC().Truncate(time.Second)
	if _, err := s.db.Exec(`UPDATE links SET burned_at=? WHERE id=?`, formatTime(exact), id); err != nil {
		t.Fatalf("set burned_at: %v", err)
	}
	// burned_at < before 严格小于，等于边界的行不应被删除。
	n, err := s.PurgeExpiredBurned(exact)
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != 0 {
		t.Fatalf("PurgeExpiredBurned at exact boundary deleted %d, want 0", n)
	}
	n2, err := s.PurgeExpiredBurned(exact.Add(time.Second))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n2 != 1 {
		t.Fatalf("PurgeExpiredBurned after boundary deleted %d, want 1", n2)
	}
}

func TestListLinksPaginationDeep3(t *testing.T) {
	s := newDeep3Store(t)
	for i := 0; i < 5; i++ {
		deep3Create(t, s, "pg"+string(rune('a'+i)), "https://example.com/"+string(rune('a'+i)))
	}
	got, total, err := s.ListLinks("", 1, 2, "created_at")
	if err != nil {
		t.Fatalf("ListLinks page1: %v", err)
	}
	if total != 5 {
		t.Fatalf("total = %d, want 5", total)
	}
	if len(got) != 2 {
		t.Fatalf("page1 len = %d, want 2", len(got))
	}
	got2, _, err := s.ListLinks("", 3, 2, "created_at")
	if err != nil {
		t.Fatalf("ListLinks page3: %v", err)
	}
	if len(got2) != 1 {
		t.Fatalf("page3 len = %d, want 1", len(got2))
	}
}

func TestListLinksPerPageClampDeep3(t *testing.T) {
	s := newDeep3Store(t)
	for i := 0; i < 3; i++ {
		deep3Create(t, s, "clamp"+string(rune('a'+i)), "https://example.com")
	}
	// perPage<1 应回落为 20。
	got, total, err := s.ListLinks("", 1, 0, "created_at")
	if err != nil {
		t.Fatalf("ListLinks perPage0: %v", err)
	}
	if total != 3 {
		t.Fatalf("total = %d, want 3", total)
	}
	if len(got) != 3 {
		t.Fatalf("perPage0 len = %d, want 3", len(got))
	}
	// page<1 应回落为 1。
	got2, _, err := s.ListLinks("", -5, 10, "created_at")
	if err != nil {
		t.Fatalf("ListLinks pageNeg: %v", err)
	}
	if len(got2) != 3 {
		t.Fatalf("pageNeg len = %d, want 3", len(got2))
	}
}

func TestListLinksInvalidOrderByDeep3(t *testing.T) {
	s := newDeep3Store(t)
	deep3Create(t, s, "ob1", "https://example.com")
	deep3Create(t, s, "ob2", "https://example.com")
	got, total, err := s.ListLinks("", 1, 10, "DROP TABLE links")
	if err != nil {
		t.Fatalf("ListLinks invalid order: %v", err)
	}
	if total != 2 {
		t.Fatalf("total = %d, want 2", total)
	}
	if len(got) != 2 {
		t.Fatalf("len = %d, want 2", len(got))
	}
}

func TestListLinksOrderByClicksDeep3(t *testing.T) {
	s := newDeep3Store(t)
	low := deep3Create(t, s, "lowclick", "https://example.com/low")
	high := deep3Create(t, s, "highclick", "https://example.com/high")
	if err := s.RecordVisit(high, "h1", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit: %v", err)
	}
	if err := s.RecordVisit(high, "h2", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit: %v", err)
	}
	if err := s.RecordVisit(low, "h3", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit: %v", err)
	}
	got, total, err := s.ListLinks("", 1, 10, "clicks")
	if err != nil {
		t.Fatalf("ListLinks: %v", err)
	}
	if total != 2 {
		t.Fatalf("total = %d, want 2", total)
	}
	if len(got) != 2 {
		t.Fatalf("len = %d, want 2", len(got))
	}
	if got[0].Slug != "highclick" {
		t.Fatalf("first slug = %q, want highclick", got[0].Slug)
	}
}

func TestListLinksSearchNoMatchDeep3(t *testing.T) {
	s := newDeep3Store(t)
	deep3Create(t, s, "searchme", "https://example.com")
	got, total, err := s.ListLinks("zzzznotfound", 1, 10, "created_at")
	if err != nil {
		t.Fatalf("ListLinks: %v", err)
	}
	if total != 0 {
		t.Fatalf("total = %d, want 0", total)
	}
	if len(got) != 0 {
		t.Fatalf("len = %d, want 0", len(got))
	}
}

func TestRecordVisitIncrementsClicksDeep3(t *testing.T) {
	s := newDeep3Store(t)
	id := deep3Create(t, s, "visitinc", "https://example.com")
	if err := s.RecordVisitGeo(id, "iphash", "ua", "ref", "CN", "China", "Zhejiang", "Hangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	got, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if got.Clicks != 1 {
		t.Fatalf("Clicks = %d, want 1", got.Clicks)
	}
}

func TestRecordVisitMissingLinkDeep3(t *testing.T) {
	s := newDeep3Store(t)
	// 无外键约束时，向不存在的 link_id 插入 visits 会成功或失败，但不应 panic。
	// 这里只验证调用不会 panic 且返回的 error 类型稳定。
	err := s.RecordVisit(555555, "ip", "ua", "ref")
	if err != nil {
		if !strings.Contains(err.Error(), "insert visit") && !strings.Contains(err.Error(), "increment clicks") {
			t.Fatalf("unexpected error: %v", err)
		}
	}
}

func TestStatsOverviewEmptyDeep3(t *testing.T) {
	s := newDeep3Store(t)
	links, enabled, clicks, today, err := s.StatsOverview()
	if err != nil {
		t.Fatalf("StatsOverview: %v", err)
	}
	if links != 0 || enabled != 0 || clicks != 0 || today != 0 {
		t.Fatalf("empty stats = (%d,%d,%d,%d), want all 0", links, enabled, clicks, today)
	}
}

func TestStatsOverviewMixedDeep3(t *testing.T) {
	s := newDeep3Store(t)
	a := deep3Create(t, s, "stat-a", "https://example.com/a")
	b := deep3Create(t, s, "stat-b", "https://example.com/b")
	// 禁用 b。
	if err := s.UpdateLinkEx(b, "t", false, nil, nil, false, false); err != nil {
		t.Fatalf("UpdateLinkEx: %v", err)
	}
	if err := s.RecordVisit(a, "ip1", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit: %v", err)
	}
	if err := s.RecordVisit(a, "ip2", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit: %v", err)
	}
	links, enabled, clicks, today, err := s.StatsOverview()
	if err != nil {
		t.Fatalf("StatsOverview: %v", err)
	}
	if links != 2 {
		t.Fatalf("links = %d, want 2", links)
	}
	if enabled != 1 {
		t.Fatalf("enabled = %d, want 1", enabled)
	}
	if clicks != 2 {
		t.Fatalf("clicks = %d, want 2", clicks)
	}
	if today != 2 {
		t.Fatalf("today = %d, want 2", today)
	}
}

func TestDailyClicksClampAndFillDeep3(t *testing.T) {
	s := newDeep3Store(t)
	// days<1 应被 clamp 为 1。
	out, err := s.DailyClicks(0)
	if err != nil {
		t.Fatalf("DailyClicks(0): %v", err)
	}
	if len(out) != 1 {
		t.Fatalf("DailyClicks(0) len = %d, want 1", len(out))
	}
	// 5 天窗口，无数据时应补 0。
	out5, err := s.DailyClicks(5)
	if err != nil {
		t.Fatalf("DailyClicks(5): %v", err)
	}
	if len(out5) != 5 {
		t.Fatalf("DailyClicks(5) len = %d, want 5", len(out5))
	}
	for _, d := range out5 {
		if d.Clicks != 0 {
			t.Fatalf("day %s clicks = %d, want 0", d.Date, d.Clicks)
		}
		if len(d.Date) != 10 {
			t.Fatalf("date %q not YYYY-MM-DD", d.Date)
		}
	}
}

func TestLinkDailyClicksScopedDeep3(t *testing.T) {
	s := newDeep3Store(t)
	a := deep3Create(t, s, "dly-a", "https://example.com/a")
	b := deep3Create(t, s, "dly-b", "https://example.com/b")
	if err := s.RecordVisit(a, "ip1", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit a: %v", err)
	}
	if err := s.RecordVisit(b, "ip2", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit b: %v", err)
	}
	out, err := s.LinkDailyClicks(a, 3)
	if err != nil {
		t.Fatalf("LinkDailyClicks: %v", err)
	}
	if len(out) != 3 {
		t.Fatalf("len = %d, want 3", len(out))
	}
	var sum int64
	for _, d := range out {
		sum += d.Clicks
	}
	if sum != 1 {
		t.Fatalf("sum clicks = %d, want 1", sum)
	}
}

func TestTopLinksClampAndOrderDeep3(t *testing.T) {
	s := newDeep3Store(t)
	a := deep3Create(t, s, "top-a", "https://example.com/a")
	b := deep3Create(t, s, "top-b", "https://example.com/b")
	if err := s.RecordVisit(b, "ip1", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit b1: %v", err)
	}
	if err := s.RecordVisit(b, "ip2", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit b2: %v", err)
	}
	if err := s.RecordVisit(a, "ip3", "ua", "ref"); err != nil {
		t.Fatalf("RecordVisit a: %v", err)
	}
	// n<1 clamp 为 1。
	out, err := s.TopLinks(0)
	if err != nil {
		t.Fatalf("TopLinks(0): %v", err)
	}
	if len(out) != 1 {
		t.Fatalf("TopLinks(0) len = %d, want 1", len(out))
	}
	if out[0].Name != "top-b" {
		t.Fatalf("top name = %q, want top-b", out[0].Name)
	}
	if out[0].Clicks != 2 {
		t.Fatalf("top clicks = %d, want 2", out[0].Clicks)
	}
}

func TestTopReferersDirectAndEmptyDeep3(t *testing.T) {
	s := newDeep3Store(t)
	id := deep3Create(t, s, "ref-link", "https://example.com")
	// 空 referer 应显示为 (direct)。
	if err := s.RecordVisit(id, "ip1", "ua", ""); err != nil {
		t.Fatalf("RecordVisit empty ref: %v", err)
	}
	if err := s.RecordVisit(id, "ip2", "ua", "https://ref.example.com"); err != nil {
		t.Fatalf("RecordVisit ref: %v", err)
	}
	out, err := s.TopReferers(10)
	if err != nil {
		t.Fatalf("TopReferers: %v", err)
	}
	if len(out) != 2 {
		t.Fatalf("len = %d, want 2", len(out))
	}
	foundDirect := false
	for _, st := range out {
		if st.Name == "(direct)" {
			foundDirect = true
			if st.Clicks != 1 {
				t.Fatalf("direct clicks = %d, want 1", st.Clicks)
			}
		}
	}
	if !foundDirect {
		t.Fatalf("expected (direct) entry, got %+v", out)
	}
}

func TestTopReferersEmptyDBDeep3(t *testing.T) {
	s := newDeep3Store(t)
	out, err := s.TopReferers(5)
	if err != nil {
		t.Fatalf("TopReferers: %v", err)
	}
	if len(out) != 0 {
		t.Fatalf("len = %d, want 0", len(out))
	}
}

func TestGeoStatsEmptyDeep3(t *testing.T) {
	s := newDeep3Store(t)
	ov, err := s.GeoStats(0, 0, "", 0)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if ov.TotalClicks != 0 {
		t.Fatalf("TotalClicks = %d, want 0", ov.TotalClicks)
	}
	if ov.TotalUV != 0 {
		t.Fatalf("TotalUV = %d, want 0", ov.TotalUV)
	}
	if len(ov.Items) != 0 {
		t.Fatalf("Items len = %d, want 0", len(ov.Items))
	}
	if ov.Days != 0 {
		t.Fatalf("Days = %d, want 0", ov.Days)
	}
}

func TestGeoStatsUnknownPctDeep3(t *testing.T) {
	s := newDeep3Store(t)
	id := deep3Create(t, s, "geo-unknown", "https://example.com")
	// 两条 unknown，两条 CN。
	if err := s.RecordVisitGeo(id, "u1", "ua", "ref", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo u1: %v", err)
	}
	if err := s.RecordVisitGeo(id, "u2", "ua", "ref", "unknown", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo u2: %v", err)
	}
	if err := s.RecordVisitGeo(id, "c1", "ua", "ref", "CN", "China", "Zhejiang", "Hangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo c1: %v", err)
	}
	if err := s.RecordVisitGeo(id, "c2", "ua", "ref", "US", "United States", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo c2: %v", err)
	}
	ov, err := s.GeoStats(id, 0, "", 8)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if ov.TotalClicks != 4 {
		t.Fatalf("TotalClicks = %d, want 4", ov.TotalClicks)
	}
	if ov.TotalUV != 4 {
		t.Fatalf("TotalUV = %d, want 4", ov.TotalUV)
	}
	if ov.UnknownPct != 50.0 {
		t.Fatalf("UnknownPct = %v, want 50", ov.UnknownPct)
	}
	if len(ov.Items) != 2 {
		t.Fatalf("Items len = %d, want 2", len(ov.Items))
	}
	for _, it := range ov.Items {
		if it.CountryCode == "" || it.CountryCode == "unknown" {
			t.Fatalf("items should exclude unknown, got %+v", it)
		}
	}
}

func TestGeoStatsCountryFilterDeep3(t *testing.T) {
	s := newDeep3Store(t)
	id := deep3Create(t, s, "geo-filter", "https://example.com")
	if err := s.RecordVisitGeo(id, "cn1", "ua", "ref", "CN", "China", "Zhejiang", "Hangzhou"); err != nil {
		t.Fatalf("RecordVisitGeo cn1: %v", err)
	}
	if err := s.RecordVisitGeo(id, "us1", "ua", "ref", "US", "United States", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo us1: %v", err)
	}
	ov, err := s.GeoStats(id, 0, "CN", 8)
	if err != nil {
		t.Fatalf("GeoStats CN: %v", err)
	}
	if ov.TotalClicks != 1 {
		t.Fatalf("CN TotalClicks = %d, want 1", ov.TotalClicks)
	}
	if len(ov.Items) != 1 {
		t.Fatalf("CN Items len = %d, want 1", len(ov.Items))
	}
	if ov.Items[0].CountryCode != "CN" {
		t.Fatalf("country = %q, want CN", ov.Items[0].CountryCode)
	}
}

func TestGeoStatsUVExcludesEmptyIPHashDeep3(t *testing.T) {
	s := newDeep3Store(t)
	id := deep3Create(t, s, "geo-uv", "https://example.com")
	if err := s.RecordVisitGeo(id, "", "ua", "ref", "CN", "China", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo empty hash: %v", err)
	}
	if err := s.RecordVisitGeo(id, "hash1", "ua", "ref", "CN", "China", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo hash1: %v", err)
	}
	ov, err := s.GeoStats(id, 0, "", 8)
	if err != nil {
		t.Fatalf("GeoStats: %v", err)
	}
	if ov.TotalClicks != 2 {
		t.Fatalf("TotalClicks = %d, want 2", ov.TotalClicks)
	}
	// 空 ip_hash 不应计入 UV。
	if ov.TotalUV != 1 {
		t.Fatalf("TotalUV = %d, want 1", ov.TotalUV)
	}
}

func TestGeoStatsNClampDeep3(t *testing.T) {
	s := newDeep3Store(t)
	id := deep3Create(t, s, "geo-nclamp", "https://example.com")
	// 造 3 个国家。
	if err := s.RecordVisitGeo(id, "a", "ua", "ref", "AA", "A", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo AA: %v", err)
	}
	if err := s.RecordVisitGeo(id, "b", "ua", "ref", "BB", "B", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo BB: %v", err)
	}
	if err := s.RecordVisitGeo(id, "c", "ua", "ref", "CC", "C", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo CC: %v", err)
	}
	// n<=0 clamp 为 8，所以应拿到全部 3 条。
	ov, err := s.GeoStats(id, 0, "", 0)
	if err != nil {
		t.Fatalf("GeoStats n0: %v", err)
	}
	if len(ov.Items) != 3 {
		t.Fatalf("Items len = %d, want 3", len(ov.Items))
	}
}

func TestGeoStatsDaysFilterDeep3(t *testing.T) {
	s := newDeep3Store(t)
	id := deep3Create(t, s, "geo-days", "https://example.com")
	// 造一条很老的 visit。
	if _, err := s.db.Exec(
		`INSERT INTO visits (link_id, ts, ip_hash, ua, referer, country_code, country_name, province, city)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		id, formatTime(time.Now().UTC().AddDate(0, 0, -30)), "old", "ua", "ref", "CN", "China", "", "",
	); err != nil {
		t.Fatalf("insert old visit: %v", err)
	}
	if err := s.RecordVisitGeo(id, "new", "ua", "ref", "CN", "China", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo new: %v", err)
	}
	ov, err := s.GeoStats(id, 7, "", 8)
	if err != nil {
		t.Fatalf("GeoStats days7: %v", err)
	}
	if ov.TotalClicks != 1 {
		t.Fatalf("days7 TotalClicks = %d, want 1", ov.TotalClicks)
	}
	if ov.Days != 7 {
		t.Fatalf("Days = %d, want 7", ov.Days)
	}
}

func TestImportCSVHeaderAndInvalidRowsDeep3(t *testing.T) {
	s := newDeep3Store(t)
	csvData := strings.Join([]string{
		"slug,url,title,enabled,expires_at,max_visits,burn",
		"imp-a,https://example.com/a,Title A,true,,,",
		"imp-b,ftp://example.com/b,Bad URL,true,,,",
		"imp-c,https://example.com/c,C,notabool,,,",
		"imp-d,https://example.com/d,D,true,,notanint,",
		"imp-e,https://example.com/e,E,true,,,true",
	}, "\n") + "\n"

	imported, skipped, errs := s.ImportCSV(strings.NewReader(csvData))
	if imported != 2 {
		t.Fatalf("imported = %d, want 2 (imp-a and imp-e)", imported)
	}
	if skipped != 3 {
		t.Fatalf("skipped = %d, want 3", skipped)
	}
	if len(errs) != 3 {
		t.Fatalf("errs len = %d, want 3, got %v", len(errs), errs)
	}
	// imp-a 应存在。
	if _, err := s.GetLinkBySlug("imp-a"); err != nil {
		t.Fatalf("imp-a missing: %v", err)
	}
	// imp-e burn=true。
	gotE, err := s.GetLinkBySlug("imp-e")
	if err != nil {
		t.Fatalf("imp-e missing: %v", err)
	}
	if !gotE.Burn {
		t.Fatalf("imp-e Burn = false, want true")
	}
}

func TestImportCSVTooFewColumnsDeep3(t *testing.T) {
	s := newDeep3Store(t)
	csvData := "onlyone\n"
	imported, skipped, errs := s.ImportCSV(strings.NewReader(csvData))
	if imported != 0 {
		t.Fatalf("imported = %d, want 0", imported)
	}
	if skipped != 1 {
		t.Fatalf("skipped = %d, want 1", skipped)
	}
	if len(errs) != 1 {
		t.Fatalf("errs len = %d, want 1", len(errs))
	}
	if !strings.Contains(errs[0], "expected at least 2 columns") {
		t.Fatalf("err msg = %q", errs[0])
	}
}

func TestImportCSVBurnConflictDeep3(t *testing.T) {
	s := newDeep3Store(t)
	// burn=true 但 max_visits=5，应冲突跳过。
	csvData := "cf-a,https://example.com/a,T,true,,5,true\n"
	imported, skipped, errs := s.ImportCSV(strings.NewReader(csvData))
	if imported != 0 {
		t.Fatalf("imported = %d, want 0", imported)
	}
	if skipped != 1 {
		t.Fatalf("skipped = %d, want 1", skipped)
	}
	if len(errs) != 1 {
		t.Fatalf("errs len = %d, want 1", len(errs))
	}
	if !strings.Contains(errs[0], "burn cannot combine") {
		t.Fatalf("err msg = %q", errs[0])
	}
}

func TestImportCSVEmptyURLDeep3(t *testing.T) {
	s := newDeep3Store(t)
	csvData := "eu-a,,T,true,,,\n"
	imported, skipped, errs := s.ImportCSV(strings.NewReader(csvData))
	if imported != 0 {
		t.Fatalf("imported = %d, want 0", imported)
	}
	if skipped != 1 {
		t.Fatalf("skipped = %d, want 1", skipped)
	}
	if len(errs) != 1 {
		t.Fatalf("errs len = %d, want 1", len(errs))
	}
	if !strings.Contains(errs[0], "empty url") {
		t.Fatalf("err msg = %q", errs[0])
	}
}

func TestExportCSVRoundTripDeep3(t *testing.T) {
	s := newDeep3Store(t)
	exp := time.Now().UTC().Add(48 * time.Hour).Truncate(time.Second)
	max := int64(3)
	if _, err := s.CreateLinkEx("exp-a", "https://example.com/a", "Title A", &exp, &max, false, false); err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if _, err := s.CreateLinkEx("exp-b", "https://example.com/b", "", nil, nil, true, false); err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	var buf bytes.Buffer
	if err := s.ExportCSV(&buf); err != nil {
		t.Fatalf("ExportCSV: %v", err)
	}
	out := buf.String()
	if !strings.HasPrefix(out, "slug,url,title,enabled,expires_at,max_visits,burn") {
		t.Fatalf("export header missing: %q", out)
	}
	if !strings.Contains(out, "exp-a") {
		t.Fatalf("export missing exp-a: %q", out)
	}
	if !strings.Contains(out, "exp-b") {
		t.Fatalf("export missing exp-b: %q", out)
	}
	if !strings.Contains(out, "true") {
		t.Fatalf("export missing true: %q", out)
	}
}

func TestExportCSVEmptyDBDeep3(t *testing.T) {
	s := newDeep3Store(t)
	var buf bytes.Buffer
	if err := s.ExportCSV(&buf); err != nil {
		t.Fatalf("ExportCSV: %v", err)
	}
	out := strings.TrimSpace(buf.String())
	if out != "slug,url,title,enabled,expires_at,max_visits,burn" {
		t.Fatalf("empty export = %q", out)
	}
}

func TestPingDeep3(t *testing.T) {
	s := newDeep3Store(t)
	if err := s.Ping(); err != nil {
		t.Fatalf("Ping: %v", err)
	}
}

func TestCreateLinkWithExpiresDeep3(t *testing.T) {
	s := newDeep3Store(t)
	exp := time.Now().UTC().Add(2 * time.Hour).Truncate(time.Second)
	id, err := s.CreateLink("exp-now", "https://example.com/exp", "T", &exp)
	if err != nil {
		t.Fatalf("CreateLink: %v", err)
	}
	got, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if got.ExpiresAt == nil {
		t.Fatalf("ExpiresAt = nil, want non-nil")
	}
	if !got.ExpiresAt.UTC().Equal(exp) {
		t.Fatalf("ExpiresAt = %v, want %v", got.ExpiresAt.UTC(), exp)
	}
	if !got.Enabled {
		t.Fatalf("Enabled = false, want true")
	}
	if got.Clicks != 0 {
		t.Fatalf("Clicks = %d, want 0", got.Clicks)
	}
}

func TestUpdateLinkSimpleDeep3(t *testing.T) {
	s := newDeep3Store(t)
	id := deep3Create(t, s, "upd-simple", "https://example.com")
	if err := s.UpdateLink(id, "renamed", false, nil); err != nil {
		t.Fatalf("UpdateLink: %v", err)
	}
	got, err := s.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if got.Title != "renamed" {
		t.Fatalf("Title = %q, want renamed", got.Title)
	}
	if got.Enabled {
		t.Fatalf("Enabled = true, want false")
	}
}

func TestListLinksSearchByTitleDeep3(t *testing.T) {
	s := newDeep3Store(t)
	if _, err := s.CreateLinkEx("srch-a", "https://example.com/a", "findme-title", nil, nil, false, false); err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if _, err := s.CreateLinkEx("srch-b", "https://example.com/b", "other", nil, nil, false, false); err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	got, total, err := s.ListLinks("findme", 1, 10, "created_at")
	if err != nil {
		t.Fatalf("ListLinks: %v", err)
	}
	if total != 1 {
		t.Fatalf("total = %d, want 1", total)
	}
	if len(got) != 1 {
		t.Fatalf("len = %d, want 1", len(got))
	}
	if got[0].Slug != "srch-a" {
		t.Fatalf("slug = %q, want srch-a", got[0].Slug)
	}
}

func TestListLinksSearchByURLDeep3(t *testing.T) {
	s := newDeep3Store(t)
	if _, err := s.CreateLinkEx("url-a", "https://unique-domain-xyz.example.com/page", "t", nil, nil, false, false); err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	got, total, err := s.ListLinks("unique-domain-xyz", 1, 10, "created_at")
	if err != nil {
		t.Fatalf("ListLinks: %v", err)
	}
	if total != 1 {
		t.Fatalf("total = %d, want 1", total)
	}
	if len(got) != 1 {
		t.Fatalf("len = %d, want 1", len(got))
	}
}
