package handler

import (
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/auth"
	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestExpiryR2_ExpiredPasswordLinkNoPage(t *testing.T) {
	st, h := newDeep3Router(t)

	hash, _ := auth.HashPassword("pw12345678")
	past := time.Now().Add(-time.Hour)
	link := &model.Link{Slug: "b2ew1", URL: "https://example.com/w1", Enabled: true, PasswordHash: &hash, ExpiresAt: &past}
	mkLinkDeep3(t, st, link)

	rec := doDeep3(t, h, http.MethodGet, "/b2ew1", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("expected status %d, got %d", http.StatusGone, rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "链接已过期") {
		t.Fatalf("expected body to contain %q, got %q", "链接已过期", rec.Body.String())
	}
}

func TestExpiryR2_ExpiredPasswordPost410(t *testing.T) {
	st, h := newDeep3Router(t)

	hash, _ := auth.HashPassword("pw12345678")
	past := time.Now().Add(-time.Hour)
	link := &model.Link{Slug: "b2ew1", URL: "https://example.com/w1", Enabled: true, PasswordHash: &hash, ExpiresAt: &past}
	mkLinkDeep3(t, st, link)

	rec := doDeep3(t, h, http.MethodPost, "/b2ew1", nil, "password=pw12345678")
	if rec.Code != http.StatusGone {
		t.Fatalf("expected status %d, got %d", http.StatusGone, rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "链接已过期") {
		t.Fatalf("expected body to contain %q, got %q", "链接已过期", rec.Body.String())
	}
}

func TestExpiryR2_ExpiredPasswordNotConsumed(t *testing.T) {
	st, h := newDeep3Router(t)

	hash, _ := auth.HashPassword("pw12345678")
	past := time.Now().Add(-time.Hour)
	link := &model.Link{Slug: "b2ew2", URL: "https://example.com/w2", Enabled: true, Burn: true, PasswordHash: &hash, ExpiresAt: &past}
	mkLinkDeep3(t, st, link)

	rec := doDeep3(t, h, http.MethodPost, "/b2ew2", nil, "password=pw12345678")
	if rec.Code != http.StatusGone {
		t.Fatalf("expected status %d, got %d", http.StatusGone, rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "链接已过期") {
		t.Fatalf("expected body to contain %q, got %q", "链接已过期", rec.Body.String())
	}

	got, err := st.GetLinkBySlug("b2ew2")
	if err != nil {
		t.Fatalf("GetLinkBySlug failed: %v", err)
	}
	if got.BurnedAt != nil {
		t.Fatalf("expected BurnedAt to be nil, got %v", got.BurnedAt)
	}
}

func TestExpiryR2_FreshPasswordLinkPage200(t *testing.T) {
	st, h := newDeep3Router(t)

	hash, _ := auth.HashPassword("pw12345678")
	future := time.Now().Add(time.Hour)
	link := &model.Link{Slug: "b2ew3", URL: "https://example.com/w3", Enabled: true, PasswordHash: &hash, ExpiresAt: &future}
	mkLinkDeep3(t, st, link)

	rec := doDeep3(t, h, http.MethodGet, "/b2ew3", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, rec.Code)
	}
}