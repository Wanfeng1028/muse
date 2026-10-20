package store

import (
	"errors"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/util"
)

func TestWlflBurnAfterRead(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("wlfl-burn1", "https://example.com/a", "", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	burned, err := st.TryBurn(id)
	if err != nil {
		t.Fatalf("TryBurn: %v", err)
	}
	if !burned {
		t.Fatalf("TryBurn first call = false, want true")
	}
	l, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if l.Enabled {
		t.Errorf("Enabled = true, want false")
	}
	if l.BurnedAt == nil {
		t.Errorf("BurnedAt = nil, want non-nil")
	}
	burned2, err := st.TryBurn(id)
	if err != nil {
		t.Fatalf("TryBurn second: %v", err)
	}
	if burned2 {
		t.Errorf("TryBurn second call = true, want false")
	}
}

func TestWlflNonBurn(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("wlfl-nonburn", "https://example.com/b", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	burned, err := st.TryBurn(id)
	if err != nil {
		t.Fatalf("TryBurn: %v", err)
	}
	if burned {
		t.Errorf("TryBurn on non-burn link = true, want false")
	}
	if err := st.MarkBurned(id); !errors.Is(err, ErrNotFound) {
		t.Errorf("MarkBurned non-burn err = %v, want ErrNotFound", err)
	}
	// burn link
	bid, err := st.CreateLinkEx("wlfl-burn2", "https://example.com/c", "", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx burn: %v", err)
	}
	if err := st.MarkBurned(bid); err != nil {
		t.Fatalf("MarkBurned burn: %v", err)
	}
	l, err := st.GetLink(bid)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if l.Enabled {
		t.Errorf("Enabled = true, want false")
	}
}

func TestWlflMaxVisits(t *testing.T) {
	st := newTestStore(t)
	mv := int64(2)
	id, err := st.CreateLinkEx("wlfl-max2", "https://example.com/d", "", nil, &mv, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	for i := 0; i < 2; i++ {
		ok, err := st.TryConsumeVisit(id)
		if err != nil {
			t.Fatalf("TryConsumeVisit %d: %v", i, err)
		}
		if !ok {
			t.Fatalf("TryConsumeVisit %d = false, want true", i)
		}
	}
	ok, err := st.TryConsumeVisit(id)
	if err != nil {
		t.Fatalf("TryConsumeVisit third: %v", err)
	}
	if ok {
		t.Errorf("TryConsumeVisit third = true, want false")
	}
	l, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if l.Clicks != 2 {
		t.Errorf("Clicks = %d, want 2", l.Clicks)
	}
	// unlimited
	uid, err := st.CreateLinkEx("wlfl-unlimited", "https://example.com/e", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx unlimited: %v", err)
	}
	for i := 0; i < 3; i++ {
		ok, err := st.TryConsumeVisit(uid)
		if err != nil {
			t.Fatalf("TryConsumeVisit unlimited %d: %v", i, err)
		}
		if !ok {
			t.Fatalf("TryConsumeVisit unlimited %d = false, want true", i)
		}
	}
}

func TestWlflExpires(t *testing.T) {
	st := newTestStore(t)
	past := time.Now().Add(-1 * time.Hour)
	_, err := st.CreateLinkEx("wlfl-expired", "https://example.com/f", "", &past, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	l, err := st.GetLinkBySlug("wlfl-expired")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if l.ExpiresAt == nil {
		t.Fatalf("ExpiresAt = nil, want non-nil")
	}
	if !l.ExpiresAt.Before(time.Now()) {
		t.Errorf("ExpiresAt = %v, want before now", l.ExpiresAt)
	}
	// nil expires
	nid, err := st.CreateLinkEx("wlfl-noexp", "https://example.com/g", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx nil exp: %v", err)
	}
	nl, err := st.GetLink(nid)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if nl.ExpiresAt != nil {
		t.Errorf("ExpiresAt = %v, want nil", nl.ExpiresAt)
	}
	// purge expired
	n, err := st.PurgeExpiredLinks(time.Now())
	if err != nil {
		t.Fatalf("PurgeExpiredLinks: %v", err)
	}
	if n != 1 {
		t.Errorf("PurgeExpiredLinks = %d, want 1", n)
	}
	// non-expired not deleted
	future := time.Now().Add(1 * time.Hour)
	fid, err := st.CreateLinkEx("wlfl-future", "https://example.com/h", "", &future, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx future: %v", err)
	}
	n2, err := st.PurgeExpiredLinks(time.Now())
	if err != nil {
		t.Fatalf("PurgeExpiredLinks second: %v", err)
	}
	if n2 != 0 {
		t.Errorf("PurgeExpiredLinks second = %d, want 0", n2)
	}
	_ = fid
}

func TestWlflVisitGeo(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("wlfl-geo", "https://example.com/i", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	err = st.RecordVisitGeo(id, "iph-1", "TestUA/1.0", "https://ref.example/", "CN", "中国", "浙江", "杭州")
	if err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	var (
		ua, ipHash, referer, cc, cn, prov, city, ts string
	)
	err = st.db.QueryRow(
		`SELECT ua, ip_hash, referer, country_code, country_name, province, city, ts FROM visits WHERE link_id = ?`,
		id,
	).Scan(&ua, &ipHash, &referer, &cc, &cn, &prov, &city, &ts)
	if err != nil {
		t.Fatalf("query visits: %v", err)
	}
	if ua != "TestUA/1.0" {
		t.Errorf("ua = %q, want TestUA/1.0", ua)
	}
	if ipHash != "iph-1" {
		t.Errorf("ip_hash = %q, want iph-1", ipHash)
	}
	if referer != "https://ref.example/" {
		t.Errorf("referer = %q, want https://ref.example/", referer)
	}
	if cc != "CN" {
		t.Errorf("country_code = %q, want CN", cc)
	}
	if ts == "" {
		t.Errorf("ts is empty")
	}
	l, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if l.Clicks != 1 {
		t.Errorf("Clicks = %d, want 1", l.Clicks)
	}
	// RecordVisitNoCount
	err = st.RecordVisitNoCount(id, "iph-2", "TestUA/2.0", "", "", "", "", "")
	if err != nil {
		t.Fatalf("RecordVisitNoCount: %v", err)
	}
	var count int64
	err = st.db.QueryRow(`SELECT COUNT(*) FROM visits WHERE link_id = ?`, id).Scan(&count)
	if err != nil {
		t.Fatalf("count visits: %v", err)
	}
	if count != 2 {
		t.Errorf("visits count = %d, want 2", count)
	}
	l2, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink after no count: %v", err)
	}
	if l2.Clicks != 1 {
		t.Errorf("Clicks after RecordVisitNoCount = %d, want 1", l2.Clicks)
	}
}

func TestWlflSlugConflict(t *testing.T) {
	st := newTestStore(t)
	_, err := st.CreateLinkEx("wlfl-dup", "https://example.com/j", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx first: %v", err)
	}
	_, err = st.CreateLinkEx("wlfl-dup", "https://example.com/k", "", nil, nil, false, false)
	if err == nil {
		t.Fatalf("CreateLinkEx second err = nil, want non-nil")
	}
	// auto slug
	id1, err := st.CreateLinkEx("", "https://example.com/l", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx auto1: %v", err)
	}
	id2, err := st.CreateLinkEx("", "https://example.com/m", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx auto2: %v", err)
	}
	l1, err := st.GetLink(id1)
	if err != nil {
		t.Fatalf("GetLink1: %v", err)
	}
	l2, err := st.GetLink(id2)
	if err != nil {
		t.Fatalf("GetLink2: %v", err)
	}
	if l1.Slug == l2.Slug {
		t.Errorf("auto slugs equal: %q", l1.Slug)
	}
	for _, l := range []*model.Link{l1, l2} {
		if len(l.Slug) != 6 {
			t.Errorf("slug %q length = %d, want 6", l.Slug, len(l.Slug))
		}
		if !util.IsValidSlug(l.Slug) {
			t.Errorf("slug %q invalid", l.Slug)
		}
	}
}

func TestWlflInvalidInput(t *testing.T) {
	st := newTestStore(t)
	_, err := st.CreateLinkEx("a b", "https://example.com/n", "", nil, nil, false, false)
	if !errors.Is(err, util.ErrInvalidSlug) {
		t.Errorf("slug with space err = %v, want util.ErrInvalidSlug", err)
	}
	longSlug := ""
	for i := 0; i < 65; i++ {
		longSlug += "a"
	}
	_, err = st.CreateLinkEx(longSlug, "https://example.com/o", "", nil, nil, false, false)
	if !errors.Is(err, util.ErrInvalidSlug) {
		t.Errorf("65-char slug err = %v, want util.ErrInvalidSlug", err)
	}
	_, err = st.CreateLinkEx("wlfl-ftp", "ftp://x", "", nil, nil, false, false)
	if err == nil {
		t.Errorf("ftp url err = nil, want non-nil")
	}
	_, err = st.CreateLinkEx("wlfl-empty", "", "", nil, nil, false, false)
	if err == nil {
		t.Errorf("empty url err = nil, want non-nil")
	}
}

func TestWlflBurnPurge(t *testing.T) {
	st := newTestStore(t)
	id, err := st.CreateLinkEx("wlfl-burnpurge", "https://example.com/p", "", nil, nil, true, true)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	l, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if !l.PurgeAfterBurn {
		t.Errorf("PurgeAfterBurn = false, want true")
	}
	// record a visit so we can verify cascade delete
	if err := st.RecordVisitGeo(id, "iph-3", "TestUA/3.0", "", "", "", "", ""); err != nil {
		t.Fatalf("RecordVisitGeo: %v", err)
	}
	burned, err := st.TryBurn(id)
	if err != nil {
		t.Fatalf("TryBurn: %v", err)
	}
	if !burned {
		t.Fatalf("TryBurn = false, want true")
	}
	if err := st.PurgeLink(id); err != nil {
		t.Fatalf("PurgeLink: %v", err)
	}
	_, err = st.GetLink(id)
	if !errors.Is(err, ErrNotFound) {
		t.Errorf("GetLink after purge err = %v, want ErrNotFound", err)
	}
	var count int64
	err = st.db.QueryRow(`SELECT COUNT(*) FROM visits WHERE link_id = ?`, id).Scan(&count)
	if err != nil {
		t.Fatalf("count visits: %v", err)
	}
	if count != 0 {
		t.Errorf("visits count = %d, want 0", count)
	}
}

func TestWlflPurgeExpiredBurned(t *testing.T) {
	st := newTestStore(t)
	// burned link
	bid, err := st.CreateLinkEx("wlfl-burned", "https://example.com/q", "", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx burned: %v", err)
	}
	burned, err := st.TryBurn(bid)
	if err != nil {
		t.Fatalf("TryBurn: %v", err)
	}
	if !burned {
		t.Fatalf("TryBurn = false, want true")
	}
	// non-burned burn link
	nbid, err := st.CreateLinkEx("wlfl-notburned", "https://example.com/r", "", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx not burned: %v", err)
	}
	n, err := st.PurgeExpiredBurned(time.Now().Add(time.Hour))
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != 1 {
		t.Errorf("PurgeExpiredBurned = %d, want 1", n)
	}
	// non-burned still exists
	_, err = st.GetLink(nbid)
	if err != nil {
		t.Fatalf("GetLink not burned: %v", err)
	}
}

func TestWlflNotFound(t *testing.T) {
	st := newTestStore(t)
	_, err := st.GetLinkBySlug("wlfl-not-exist")
	if !errors.Is(err, ErrNotFound) {
		t.Errorf("GetLinkBySlug err = %v, want ErrNotFound", err)
	}
	err = st.DeleteLink(999999)
	if !errors.Is(err, ErrNotFound) {
		t.Errorf("DeleteLink err = %v, want ErrNotFound", err)
	}
}
