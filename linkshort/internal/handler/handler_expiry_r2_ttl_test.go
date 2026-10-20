package handler

import (
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestExpiryR2_TTLToSecond(t *testing.T) {
	st, h := newDeep3Router(t)
	exp := time.Now().Add(2 * time.Second)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2ex1", URL: "https://example.com/e1", Enabled: true, ExpiresAt: &exp})

	rec := doDeep3(t, h, http.MethodGet, "/b2ex1", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("immediate GET status = %d, want 302", rec.Code)
	}

	var got410 bool
	for i := 0; i < 30; i++ {
		time.Sleep(200 * time.Millisecond)
		r := doDeep3(t, h, http.MethodGet, "/b2ex1", nil, "")
		if r.Code == http.StatusGone {
			if !strings.Contains(r.Body.String(), "链接已过期") {
				t.Fatalf("410 body = %q, want contains %q", r.Body.String(), "链接已过期")
			}
			got410 = true
			break
		}
	}
	if !got410 {
		t.Fatalf("link did not expire to 410 within polling window")
	}
}

func TestExpiryR2_ExpiredDoesNotCountClick(t *testing.T) {
	st, h := newDeep3Router(t)
	exp := time.Now().Add(-1 * time.Second)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2ex1", URL: "https://example.com/e1", Enabled: true, ExpiresAt: &exp})

	for i := 0; i < 3; i++ {
		rec := doDeep3(t, h, http.MethodGet, "/b2ex1", nil, "")
		if rec.Code != http.StatusGone {
			t.Fatalf("expired GET #%d status = %d, want 410", i, rec.Code)
		}
	}

	link, err := st.GetLinkBySlug("b2ex1")
	if err != nil {
		t.Fatalf("GetLinkBySlug error: %v", err)
	}
	if link.Clicks != 0 {
		t.Fatalf("Clicks = %d, want 0 (expired requests must not count)", link.Clicks)
	}
}

func TestExpiryR2_ExpiredBurnNotConsumed(t *testing.T) {
	st, h := newDeep3Router(t)
	exp := time.Now().Add(-1 * time.Hour)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2ex2", URL: "https://example.com/e2", Enabled: true, Burn: true, ExpiresAt: &exp})

	rec := doDeep3(t, h, http.MethodGet, "/b2ex2", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("status = %d, want 410", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "链接已过期") {
		t.Fatalf("body = %q, want contains %q", rec.Body.String(), "链接已过期")
	}

	link, err := st.GetLinkBySlug("b2ex2")
	if err != nil {
		t.Fatalf("GetLinkBySlug error: %v", err)
	}
	if !link.Enabled {
		t.Fatalf("Enabled = false, want true (burn slot must not be consumed)")
	}
	if link.BurnedAt != nil {
		t.Fatalf("BurnedAt = %v, want nil", link.BurnedAt)
	}
}

func TestExpiryR2_FarFutureRedirects(t *testing.T) {
	st, h := newDeep3Router(t)
	exp := time.Now().Add(8760 * time.Hour)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2ex3", URL: "https://example.com/e3", Enabled: true, ExpiresAt: &exp})

	rec := doDeep3(t, h, http.MethodGet, "/b2ex3", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("status = %d, want 302", rec.Code)
	}
}