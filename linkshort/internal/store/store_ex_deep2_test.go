package store

import (
	"errors"
	"path/filepath"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	dbpkg "github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/util"
)

func newDeep2Store(t *testing.T) *Store {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "deep2.db")
	db, err := dbpkg.Open(dbPath)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	s := New(db)
	return s
}

func mustCreateLinkDeep2(t *testing.T, s *Store, slug, url string) int64 {
	t.Helper()
	id, err := s.CreateLinkEx(slug, url, "t", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx(%q,%q): %v", slug, url, err)
	}
	return id
}

func TestCreateLinkExInvalidURLDeep2(t *testing.T) {
	s := newDeep2Store(t)

	if _, err := s.CreateLinkEx("", "", "t", nil, nil, false, false); err == nil {
		t.Fatalf("expected error for empty url")
	} else if err.Error() != "url must start with http:// or https://" {
		t.Fatalf("empty url err = %q", err.Error())
	}

	if _, err := s.CreateLinkEx("", "ftp://example.com", "t", nil, nil, false, false); err == nil {
		t.Fatalf("expected error for ftp url")
	} else if err.Error() != "url must start with http:// or https://" {
		t.Fatalf("ftp url err = %q", err.Error())
	}

	long := "http://example.com/" + string(make([]byte, 0))
	_ = long
	tooLong := "https://"
	for i := 0; i < 2049; i++ {
		tooLong += "a"
	}
	if len(tooLong) <= 2048 {
		t.Fatalf("setup: tooLong len = %d", len(tooLong))
	}
	if _, err := s.CreateLinkEx("", tooLong, "t", nil, nil, false, false); err == nil {
		t.Fatalf("expected error for overly long url")
	}
}

func TestCreateLinkExInvalidSlugDeep2(t *testing.T) {
	s := newDeep2Store(t)

	if _, err := s.CreateLinkEx("bad slug", "https://example.com", "t", nil, nil, false, false); err == nil {
		t.Fatalf("expected ErrInvalidSlug for slug with space")
	} else if !errors.Is(err, util.ErrInvalidSlug) {
		t.Fatalf("space slug err = %v, want ErrInvalidSlug", err)
	}

	tooLongSlug := ""
	for i := 0; i < 65; i++ {
		tooLongSlug += "a"
	}
	if len(tooLongSlug) != 65 {
		t.Fatalf("setup: slug len = %d", len(tooLongSlug))
	}
	if _, err := s.CreateLinkEx(tooLongSlug, "https://example.com", "t", nil, nil, false, false); err == nil {
		t.Fatalf("expected ErrInvalidSlug for 65-char slug")
	} else if !errors.Is(err, util.ErrInvalidSlug) {
		t.Fatalf("long slug err = %v, want ErrInvalidSlug", err)
	}
}

func TestCreateLinkExAutoSlugUniqueDeep2(t *testing.T) {
	s := newDeep2Store(t)

	seen := make(map[string]bool)
	for i := 0; i < 3; i++ {
		id, err := s.CreateLinkEx("", "https://example.com", "t", nil, nil, false, false)
		if err != nil {
			t.Fatalf("CreateLinkEx auto #%d: %v", i, err)
		}
		got, err := s.GetLink(id)
		if err != nil {
			t.Fatalf("GetLink #%d: %v", i, err)
		}
		if got.Slug == "" {
			t.Fatalf("auto slug #%d is empty", i)
		}
		if seen[got.Slug] {
			t.Fatalf("duplicate auto slug %q", got.Slug)
		}
		seen[got.Slug] = true

		got2, err := s.GetLinkBySlug(got.Slug)
		if err != nil {
			t.Fatalf("GetLinkBySlug(%q): %v", got.Slug, err)
		}
		if got2.ID != id {
			t.Fatalf("slug %q maps to id %d, want %d", got.Slug, got2.ID, id)
		}
	}
	if len(seen) != 3 {
		t.Fatalf("expected 3 unique auto slugs, got %d", len(seen))
	}
}

func TestCreateLinkExMaxVisitsDeep2(t *testing.T) {
	s := newDeep2Store(t)

	nilLink, err := s.CreateLinkEx("nilvisits", "https://example.com", "t", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx nil maxVisits: %v", err)
	}
	gotNil, err := s.GetLink(nilLink)
	if err != nil {
		t.Fatalf("GetLink nilLink: %v", err)
	}
	if gotNil.MaxVisits != nil {
		t.Fatalf("nil maxVisits persisted as %v, want nil", *gotNil.MaxVisits)
	}

	max := int64(7)
	someLink, err := s.CreateLinkEx("somevisits", "https://example.com", "t", nil, &max, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx some maxVisits: %v", err)
	}
	gotSome, err := s.GetLink(someLink)
	if err != nil {
		t.Fatalf("GetLink someLink: %v", err)
	}
	if gotSome.MaxVisits == nil {
		t.Fatalf("some maxVisits persisted as nil, want 7")
	}
	if *gotSome.MaxVisits != 7 {
		t.Fatalf("some maxVisits = %d, want 7", *gotSome.MaxVisits)
	}
}

func TestCreateLinkExBurnPurgeDeep2(t *testing.T) {
	s := newDeep2Store(t)

	link, err := s.CreateLinkEx("burnpurge", "https://example.com", "t", nil, nil, true, true)
	if err != nil {
		t.Fatalf("CreateLinkEx burn+purge: %v", err)
	}
	got, err := s.GetLink(link)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if !got.Burn {
		t.Fatalf("Burn = false, want true")
	}
	if !got.PurgeAfterBurn {
		t.Fatalf("PurgeAfterBurn = false, want true")
	}
}

func TestUpdateLinkExDeep2(t *testing.T) {
	s := newDeep2Store(t)

	link, err := s.CreateLinkEx("updlink", "https://example.com", "old", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}

	max := int64(11)
	newTitle := "new title"
	enabled := false
	expires := time.Now().Add(24 * time.Hour).UTC().Truncate(time.Second)
	if err := s.UpdateLinkEx(link, newTitle, enabled, &expires, &max, true, true); err != nil {
		t.Fatalf("UpdateLinkEx: %v", err)
	}

	got, err := s.GetLink(link)
	if err != nil {
		t.Fatalf("GetLink after update: %v", err)
	}
	if got.Title != newTitle {
		t.Fatalf("Title = %q, want %q", got.Title, newTitle)
	}
	if got.Enabled != false {
		t.Fatalf("Enabled = true, want false")
	}
	if got.MaxVisits == nil || *got.MaxVisits != 11 {
		t.Fatalf("MaxVisits = %v, want 11", got.MaxVisits)
	}
	if !got.Burn {
		t.Fatalf("Burn = false, want true")
	}
	if !got.PurgeAfterBurn {
		t.Fatalf("PurgeAfterBurn = false, want true")
	}
	if got.ExpiresAt == nil {
		t.Fatalf("ExpiresAt = nil, want non-nil")
	}
}

func TestMarkBurnedDeep2(t *testing.T) {
	s := newDeep2Store(t)

	link, err := s.CreateLinkEx("markburn", "https://example.com", "t", nil, nil, true, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if err := s.MarkBurned(link); err != nil {
		t.Fatalf("MarkBurned: %v", err)
	}
	got, err := s.GetLink(link)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if got.Enabled {
		t.Fatalf("Enabled = true after MarkBurned, want false")
	}
	if !got.Burn {
		t.Fatalf("Burn = false after MarkBurned, want true")
	}
}

func TestPurgeExpiredBurnedDeep2(t *testing.T) {
	s := newDeep2Store(t)

	old := time.Now().Add(-48 * time.Hour).UTC()
	recent := time.Now().Add(-1 * time.Hour).UTC()

	burnedOld, err := s.CreateLinkEx("bouncedold", "https://example.com", "t", &old, nil, true, true)
	if err != nil {
		t.Fatalf("CreateLinkEx burnedOld: %v", err)
	}
	if err := s.MarkBurned(burnedOld); err != nil {
		t.Fatalf("MarkBurned burnedOld: %v", err)
	}
	// PurgeExpiredBurned 按 burned_at 清理；把 burnedOld 的 burned_at 回拨到 30 天前
	if _, err := s.db.Exec(`UPDATE links SET burned_at=? WHERE id=?`, old.Format(time.RFC3339), burnedOld); err != nil {
		t.Fatalf("backdate burned_at: %v", err)
	}

	burnedRecent, err := s.CreateLinkEx("burnedrecent", "https://example.com", "t", &recent, nil, true, true)
	if err != nil {
		t.Fatalf("CreateLinkEx burnedRecent: %v", err)
	}
	if err := s.MarkBurned(burnedRecent); err != nil {
		t.Fatalf("MarkBurned burnedRecent: %v", err)
	}

	nonBurn, err := s.CreateLinkEx("nonburn", "https://example.com", "t", &old, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx nonBurn: %v", err)
	}

	before := time.Now().UTC()
	n, err := s.PurgeExpiredBurned(before)
	if err != nil {
		t.Fatalf("PurgeExpiredBurned: %v", err)
	}
	if n != 1 {
		t.Fatalf("PurgeExpiredBurned deleted %d, want 1", n)
	}

	if _, err := s.GetLink(burnedOld); !errors.Is(err, ErrNotFound) {
		t.Fatalf("burnedOld still present, err = %v", err)
	}
	if _, err := s.GetLink(burnedRecent); err != nil {
		t.Fatalf("burnedRecent should remain, err = %v", err)
	}
	if _, err := s.GetLink(nonBurn); err != nil {
		t.Fatalf("nonBurn should remain, err = %v", err)
	}
}

func TestPurgeLinkDeep2(t *testing.T) {
	s := newDeep2Store(t)

	link, err := s.CreateLinkEx("purgelink", "https://example.com", "t", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if err := s.PurgeLink(link); err != nil {
		t.Fatalf("PurgeLink: %v", err)
	}
	if _, err := s.GetLinkBySlug("purgelink"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetLinkBySlug after PurgeLink err = %v, want ErrNotFound", err)
	}
	if _, err := s.GetLink(link); !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetLink after PurgeLink err = %v, want ErrNotFound", err)
	}
}

func TestDeleteLinkDeep2(t *testing.T) {
	s := newDeep2Store(t)

	link, err := s.CreateLinkEx("dellink", "https://example.com", "t", nil, nil, false, false)
	if err != nil {
		t.Fatalf("CreateLinkEx: %v", err)
	}
	if err := s.DeleteLink(link); err != nil {
		t.Fatalf("DeleteLink: %v", err)
	}
	if _, err := s.GetLink(link); !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetLink after DeleteLink err = %v, want ErrNotFound", err)
	}
}
