package handler

import (
	"net/http"
	"path/filepath"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func TestLimitR2_ClicksSurviveReopen(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "persist.db")
	database, _ := db.Open(dbPath)
	st := store.New(database)
	h := NewRouter(st, &config.Config{})

	mv := int64(3)
	id, _ := st.CreateLinkEx("b2ps1", "https://example.com/ps1", "", nil, &mv, false, false)

	rec1 := doDeep3(t, h, http.MethodGet, "/b2ps1", nil, "")
	if rec1.Code != http.StatusFound {
		t.Fatalf("first GET status = %d, want %d", rec1.Code, http.StatusFound)
	}
	rec2 := doDeep3(t, h, http.MethodGet, "/b2ps1", nil, "")
	if rec2.Code != http.StatusFound {
		t.Fatalf("second GET status = %d, want %d", rec2.Code, http.StatusFound)
	}

	database.Close()

	database2, _ := db.Open(dbPath)
	st2 := store.New(database2)
	t.Cleanup(func() { database2.Close() })

	l, err := st2.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink after reopen error = %v", err)
	}
	if l == nil {
		t.Fatalf("GetLink after reopen returned nil")
	}
	if l.Clicks != 2 {
		t.Fatalf("clicks after reopen = %d, want 2", l.Clicks)
	}
	_ = model.Link{}
}

func TestLimitR2_LimitEnforcedAfterReopen(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "persist_limit.db")
	database, _ := db.Open(dbPath)
	st := store.New(database)
	h := NewRouter(st, &config.Config{})

	mv := int64(2)
	_, _ = st.CreateLinkEx("b2ps1b", "https://example.com/ps1b", "", nil, &mv, false, false)

	rec1 := doDeep3(t, h, http.MethodGet, "/b2ps1b", nil, "")
	if rec1.Code != http.StatusFound {
		t.Fatalf("first GET status = %d, want %d", rec1.Code, http.StatusFound)
	}
	rec2 := doDeep3(t, h, http.MethodGet, "/b2ps1b", nil, "")
	if rec2.Code != http.StatusFound {
		t.Fatalf("second GET status = %d, want %d", rec2.Code, http.StatusFound)
	}

	database.Close()

	database2, _ := db.Open(dbPath)
	st2 := store.New(database2)
	h2 := NewRouter(st2, &config.Config{})
	t.Cleanup(func() { database2.Close() })

	rec3 := doDeep3(t, h2, http.MethodGet, "/b2ps1b", nil, "")
	if rec3.Code != http.StatusGone {
		t.Fatalf("GET after reopen status = %d, want %d", rec3.Code, http.StatusGone)
	}
	if !contains(rec3.Body.String(), "链接已达访问上限") {
		t.Fatalf("GET after reopen body = %q, want contain %q", rec3.Body.String(), "链接已达访问上限")
	}
}

func TestLimitR2_VisitsSurviveReopen(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "persist_visits.db")
	database, _ := db.Open(dbPath)
	st := store.New(database)
	h := NewRouter(st, &config.Config{})

	mv := int64(5)
	id, _ := st.CreateLinkEx("b2ps2", "https://example.com/ps2", "", nil, &mv, false, false)

	for i := 0; i < 3; i++ {
		rec := doDeep3(t, h, http.MethodGet, "/b2ps2", nil, "")
		if rec.Code != http.StatusFound {
			t.Fatalf("GET #%d status = %d, want %d", i+1, rec.Code, http.StatusFound)
		}
	}

	database.Close()

	database2, _ := db.Open(dbPath)
	st2 := store.New(database2)
	t.Cleanup(func() { database2.Close() })

	stats, err := st2.LinkDailyClicks(id, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks after reopen error = %v", err)
	}
	var sum int64
	for _, s := range stats {
		sum += s.Clicks
	}
	if sum != 3 {
		t.Fatalf("LinkDailyClicks after reopen = %d, want 3", sum)
	}
}

func contains(s, sub string) bool {
	if len(sub) == 0 {
		return true
	}
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
