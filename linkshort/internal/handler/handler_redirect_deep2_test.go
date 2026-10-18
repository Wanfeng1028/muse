package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/auth"
	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func newDeep2Router(t *testing.T) (*store.Store, http.Handler) {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { database.Close() })
	st := store.New(database)
	cfg := config.Config{}
	h := NewRouter(st, &cfg)
	return st, h
}

func mkLinkDeep2(t *testing.T, st *store.Store, l *model.Link) int64 {
	t.Helper()
	id, err := st.CreateLinkEx(l.Slug, l.URL, l.Title, l.ExpiresAt, l.MaxVisits, l.Burn, l.PurgeAfterBurn)
	if err != nil {
		t.Fatalf("CreateLinkEx(%s): %v", l.Slug, err)
	}
	// CreateLinkEx 默认 enabled=1、无密码；按用例需求回写
	if !l.Enabled {
		if err := st.UpdateLinkEx(id, l.Title, false, l.ExpiresAt, l.MaxVisits, l.Burn, l.PurgeAfterBurn); err != nil {
			t.Fatalf("disable link: %v", err)
		}
	}
	if l.PasswordHash != nil {
		if err := st.SetLinkPassword(id, *l.PasswordHash); err != nil {
			t.Fatalf("set password: %v", err)
		}
	}
	return id
}

func doDeep2(t *testing.T, h http.Handler, method, target string, hdr map[string]string, body string) *httptest.ResponseRecorder {
	t.Helper()
	var rdr *strings.Reader
	if body != "" {
		rdr = strings.NewReader(body)
	} else {
		rdr = strings.NewReader("")
	}
	req := httptest.NewRequest(method, target, rdr)
	if method == http.MethodPost {
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	}
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	return rr
}

func TestRedirectNormal302Deep2(t *testing.T) {
	st, h := newDeep2Router(t)
	target := "https://example.com/landing"
	mkLinkDeep2(t, st, &model.Link{
		Slug:    "normal",
		URL:     target,
		Enabled: true,
	})

	rr := doDeep2(t, h, http.MethodGet, "/normal", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want 302", rr.Code)
	}
	if got := rr.Header().Get("Location"); got != target {
		t.Fatalf("Location = %q, want %q", got, target)
	}
}

func TestRedirectNotFoundDeep2(t *testing.T) {
	_, h := newDeep2Router(t)
	rr := doDeep2(t, h, http.MethodGet, "/does-not-exist", nil, "")
	if rr.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", rr.Code)
	}
}

func TestRedirectDisabled404Deep2(t *testing.T) {
	st, h := newDeep2Router(t)
	mkLinkDeep2(t, st, &model.Link{
		Slug:    "disabled",
		URL:     "https://example.com/x",
		Enabled: false,
		Burn:    false,
	})
	rr := doDeep2(t, h, http.MethodGet, "/disabled", nil, "")
	if rr.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", rr.Code)
	}
}

func TestRedirectExpired410Deep2(t *testing.T) {
	st, h := newDeep2Router(t)
	past := time.Now().Add(-1 * time.Hour)
	mkLinkDeep2(t, st, &model.Link{
		Slug:      "expired",
		URL:       "https://example.com/x",
		Enabled:   true,
		ExpiresAt: &past,
	})
	rr := doDeep2(t, h, http.MethodGet, "/expired", nil, "")
	if rr.Code != http.StatusGone {
		t.Fatalf("status = %d, want 410", rr.Code)
	}
}

func TestRedirectBurnBurned410Deep2(t *testing.T) {
	st, h := newDeep2Router(t)
	mkLinkDeep2(t, st, &model.Link{
		Slug:    "burned",
		URL:     "https://example.com/x",
		Enabled: false,
		Burn:    true,
	})
	rr := doDeep2(t, h, http.MethodGet, "/burned", nil, "")
	if rr.Code != http.StatusGone {
		t.Fatalf("status = %d, want 410", rr.Code)
	}
}

func TestRedirectMaxVisits410Deep2(t *testing.T) {
	st, h := newDeep2Router(t)
	var limit int64 = 1
	linkID := mkLinkDeep2(t, st, &model.Link{
		Slug:      "capped",
		URL:       "https://example.com/x",
		Enabled:   true,
		MaxVisits: &limit,
	})
	// 刷一次点击到上限
	if err := st.RecordVisit(linkID, "", "", ""); err != nil {
		t.Fatalf("RecordVisit: %v", err)
	}
	rr := doDeep2(t, h, http.MethodGet, "/capped", nil, "")
	if rr.Code != http.StatusGone {
		t.Fatalf("status = %d, want 410", rr.Code)
	}
}

func TestRedirectBurnOnceThen410Deep2(t *testing.T) {
	st, h := newDeep2Router(t)
	mkLinkDeep2(t, st, &model.Link{
		Slug:    "one-shot",
		URL:     "https://example.com/once",
		Enabled: true,
		Burn:    true,
	})
	first := doDeep2(t, h, http.MethodGet, "/one-shot", nil, "")
	if first.Code != http.StatusFound {
		t.Fatalf("first status = %d, want 302", first.Code)
	}
	if got := first.Header().Get("Location"); got != "https://example.com/once" {
		t.Fatalf("first Location = %q, want %q", got, "https://example.com/once")
	}
	second := doDeep2(t, h, http.MethodGet, "/one-shot", nil, "")
	if second.Code != http.StatusGone {
		t.Fatalf("second status = %d, want 410", second.Code)
	}
}

func TestPasswordGetRendersPageDeep2(t *testing.T) {
	st, h := newDeep2Router(t)
	hash, err := auth.HashPassword("s3cret")
	if err != nil {
		t.Fatalf("auth.HashPassword: %v", err)
	}
	mkLinkDeep2(t, st, &model.Link{
		Slug:         "locked",
		URL:          "https://example.com/secret",
		Enabled:      true,
		PasswordHash: &hash,
	})
	rr := doDeep2(t, h, http.MethodGet, "/locked", nil, "")
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rr.Code)
	}
	if !strings.Contains(strings.ToLower(rr.Body.String()), "password") {
		t.Fatalf("password page missing password field, body=%q", rr.Body.String())
	}
}

func TestPasswordWrongPostNoRedirectDeep2(t *testing.T) {
	st, h := newDeep2Router(t)
	hash, err := auth.HashPassword("s3cret")
	if err != nil {
		t.Fatalf("hashPassword: %v", err)
	}
	mkLinkDeep2(t, st, &model.Link{
		Slug:         "locked2",
		URL:          "https://example.com/secret2",
		Enabled:      true,
		PasswordHash: &hash,
	})
	before, err := st.GetLinkBySlug("locked2")
	if err != nil {
		t.Fatalf("GetLinkBySlug before: %v", err)
	}
	form := url.Values{}
	form.Set("password", "wrong")
	rr := doDeep2(t, h, http.MethodPost, "/locked2", nil, form.Encode())
	if rr.Code == http.StatusFound {
		t.Fatalf("wrong password should not redirect, got 302 -> %q", rr.Header().Get("Location"))
	}
	after, err := st.GetLinkBySlug("locked2")
	if err != nil {
		t.Fatalf("GetLinkBySlug after: %v", err)
	}
	if after.Clicks != before.Clicks {
		t.Fatalf("clicks changed on wrong password: before=%d after=%d", before.Clicks, after.Clicks)
	}
}

func TestPasswordCorrectPostRedirectsDeep2(t *testing.T) {
	st, h := newDeep2Router(t)
	hash, err := auth.HashPassword("s3cret")
	if err != nil {
		t.Fatalf("hashPassword: %v", err)
	}
	mkLinkDeep2(t, st, &model.Link{
		Slug:         "locked3",
		URL:          "https://example.com/secret3",
		Enabled:      true,
		PasswordHash: &hash,
	})
	form := url.Values{}
	form.Set("password", "s3cret")
	rr := doDeep2(t, h, http.MethodPost, "/locked3", nil, form.Encode())
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want 302", rr.Code)
	}
	if got := rr.Header().Get("Location"); got != "https://example.com/secret3" {
		t.Fatalf("Location = %q, want %q", got, "https://example.com/secret3")
	}
}

func TestRedirectXFFAffectsIPHashDeep2(t *testing.T) {
	st, h := newDeep2Router(t)
	mkLinkDeep2(t, st, &model.Link{
		Slug:    "xff",
		URL:     "https://example.com/xff",
		Enabled: true,
	})
	doDeep2(t, h, http.MethodGet, "/xff", map[string]string{"X-Forwarded-For": "10.0.0.1"}, "")
	doDeep2(t, h, http.MethodGet, "/xff", map[string]string{"X-Forwarded-For": "10.0.0.2"}, "")

	got, err := st.GetLinkBySlug("xff")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks < 2 {
		t.Fatalf("expected >=2 clicks, got %d", got.Clicks)
	}
}

func TestRedirectLogsVisitDeep2(t *testing.T) {
	st, h := newDeep2Router(t)
	mkLinkDeep2(t, st, &model.Link{
		Slug:    "logged",
		URL:     "https://example.com/logged",
		Enabled: true,
	})
	rr := doDeep2(t, h, http.MethodGet, "/logged", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("status = %d, want 302", rr.Code)
	}
	got, err := st.GetLinkBySlug("logged")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.Clicks != 1 {
		t.Fatalf("expected 1 click, got %d", got.Clicks)
	}
}

var _ = context.Background
