package handler

import (
	"net/http"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestExpiryR2_CreatePastExpiryAllowed(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-time.Hour)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2em1", URL: "https://example.com/m1", Enabled: true, ExpiresAt: &past})
	if id == 0 {
		t.Fatalf("expected link created with past expiry, got id 0")
	}
	rec := doDeep3(t, h, http.MethodGet, "/b2em1", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("expected 410 for expired link, got %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "链接已过期") {
		t.Fatalf("expected body to contain 链接已过期, got %s", rec.Body.String())
	}
}

func TestExpiryR2_ExpiredStillVisibleInMgmtAPI(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-time.Hour)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2em1", URL: "https://example.com/m1", Enabled: true, ExpiresAt: &past})
	rec := doDeep3(t, h, http.MethodGet, "/api/links/"+strconv.FormatInt(id, 10), nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for expired link in mgmt API, got %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "b2em1") {
		t.Fatalf("expected body to contain b2em1, got %s", rec.Body.String())
	}
}

func TestExpiryR2_ExpiredDailyStats200(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-time.Hour)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2em1", URL: "https://example.com/m1", Enabled: true, ExpiresAt: &past})
	rec := doDeep3(t, h, http.MethodGet, "/api/links/"+strconv.FormatInt(id, 10)+"/daily", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for expired link daily stats, got %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestExpiryR2_ExpiredPostUnlock410(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-time.Hour)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2em2", URL: "https://example.com/m2", Enabled: true, ExpiresAt: &past})
	rec := doDeep3(t, h, http.MethodPost, "/b2em2", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("expected 410 for expired POST unlock, got %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "链接已过期") {
		t.Fatalf("expected body to contain 链接已过期, got %s", rec.Body.String())
	}
}