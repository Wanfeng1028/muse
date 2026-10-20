package handler

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestBurnR2_PostPasswordFieldIgnoredNoPassword(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2pf1", URL: "https://example.com/f1", Enabled: true, Burn: true})

	rec := doDeep3(t, h, http.MethodPost, "/b2pf1", nil, "password=whatever")
	if rec.Code != http.StatusFound {
		t.Fatalf("expected 302, got %d", rec.Code)
	}
	if loc := rec.Header().Get("Location"); loc != "https://example.com/f1" {
		t.Fatalf("expected Location https://example.com/f1, got %q", loc)
	}
}

func TestBurnR2_PostGarbageBodyBurn(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2pf2", URL: "https://example.com/f2", Enabled: true, Burn: true})

	rec := doDeep3(t, h, http.MethodPost, "/b2pf2", nil, "not-a-form-body")
	if rec.Code != http.StatusFound {
		t.Fatalf("expected 302, got %d", rec.Code)
	}
	if loc := rec.Header().Get("Location"); !strings.HasPrefix(loc, "https://example.com/f2") {
		t.Fatalf("expected Location to start with https://example.com/f2, got %q", loc)
	}
}

func TestBurnR2_PostEmptyBodyBurn(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2pf3", URL: "https://example.com/f3", Enabled: true, Burn: true})

	rec := doDeep3(t, h, http.MethodPost, "/b2pf3", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("expected 302, got %d", rec.Code)
	}

	rec2 := doDeep3(t, h, http.MethodPost, "/b2pf3", nil, "")
	if rec2.Code != http.StatusGone {
		t.Fatalf("expected 410 on second POST, got %d", rec2.Code)
	}
}

func TestBurnR2_PostPasswordFieldIgnoredNormal(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2pf4", URL: "https://example.com/f4", Enabled: true})

	rec := doDeep3(t, h, http.MethodPost, "/b2pf4", nil, "password=whatever")
	if rec.Code != http.StatusFound {
		t.Fatalf("expected 302, got %d", rec.Code)
	}
	if loc := rec.Header().Get("Location"); loc != "https://example.com/f4" {
		t.Fatalf("expected Location https://example.com/f4, got %q", loc)
	}

	link, err := st.GetLinkBySlug("b2pf4")
	if err != nil {
		t.Fatalf("GetLinkBySlug error: %v", err)
	}
	if link == nil {
		t.Fatalf("expected link, got nil")
	}
	if link.ID != id {
		t.Fatalf("expected link ID %d, got %d", id, link.ID)
	}
	if link.Clicks != 1 {
		t.Fatalf("expected Clicks==1, got %d", link.Clicks)
	}
}