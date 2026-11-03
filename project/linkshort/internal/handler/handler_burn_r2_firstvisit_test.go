package handler

import (
	"net/http"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func TestBurnR2_FirstGetExactLocation(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { database.Close() })
	st2 := store.New(database)
	cfg := config.Config{}
	h2 := NewRouter(st2, &cfg)

	id := mkLinkDeep3(t, st2, &model.Link{
		Slug:    "b2fv1",
		URL:     "https://example.com/first?x=1&y=2",
		Enabled: true,
		Burn:    true,
	})
	_ = id

	rr := doDeep3(t, h2, http.MethodGet, "/b2fv1", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want %d", rr.Code, http.StatusFound)
	}
	if got := rr.Header().Get("Location"); got != "https://example.com/first?x=1&y=2" {
		t.Fatalf("Location = %q, want %q", got, "https://example.com/first?x=1&y=2")
	}
}

func TestBurnR2_FirstGetClicksOneVisitOne(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { database.Close() })
	st := store.New(database)
	cfg := config.Config{}
	h := NewRouter(st, &cfg)

	id := mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2fv1",
		URL:     "https://example.com/first?x=1&y=2",
		Enabled: true,
		Burn:    true,
	})

	rr := doDeep3(t, h, http.MethodGet, "/b2fv1", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want %d", rr.Code, http.StatusFound)
	}

	got, err := st.GetLinkBySlug("b2fv1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks != 1 {
		t.Fatalf("Clicks = %d, want 1", got.Clicks)
	}

	daily, err := st.LinkDailyClicks(id, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks: %v", err)
	}
	var sum int64
	for _, d := range daily {
		sum += d.Clicks
	}
	if sum != 1 {
		t.Fatalf("daily clicks sum = %d, want 1", sum)
	}
}

func TestBurnR2_SecondGetNoDoubleCount(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { database.Close() })
	st := store.New(database)
	cfg := config.Config{}
	h := NewRouter(st, &cfg)

	id := mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2fv1",
		URL:     "https://example.com/first?x=1&y=2",
		Enabled: true,
		Burn:    true,
	})

	first := doDeep3(t, h, http.MethodGet, "/b2fv1", nil, "")
	if first.Code != http.StatusFound {
		t.Fatalf("first status = %d, want %d", first.Code, http.StatusFound)
	}

	second := doDeep3(t, h, http.MethodGet, "/b2fv1", nil, "")
	if second.Code != http.StatusGone {
		t.Fatalf("second status = %d, want %d", second.Code, http.StatusGone)
	}

	got, err := st.GetLinkBySlug("b2fv1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks != 1 {
		t.Fatalf("Clicks = %d, want 1", got.Clicks)
	}

	daily, err := st.LinkDailyClicks(id, 7)
	if err != nil {
		t.Fatalf("LinkDailyClicks: %v", err)
	}
	var sum int64
	for _, d := range daily {
		sum += d.Clicks
	}
	if sum != 1 {
		t.Fatalf("daily clicks sum = %d, want 1", sum)
	}
}

func TestBurnR2_BurnedAtSetAfterFirstGet(t *testing.T) {
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { database.Close() })
	st := store.New(database)
	cfg := config.Config{}
	h := NewRouter(st, &cfg)

	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2fv1",
		URL:     "https://example.com/first?x=1&y=2",
		Enabled: true,
		Burn:    true,
	})

	rr := doDeep3(t, h, http.MethodGet, "/b2fv1", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want %d", rr.Code, http.StatusFound)
	}

	got, err := st.GetLinkBySlug("b2fv1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.BurnedAt == nil {
		t.Fatalf("BurnedAt = nil, want non-nil")
	}
	if got.Enabled {
		t.Fatalf("Enabled = true, want false")
	}
}
