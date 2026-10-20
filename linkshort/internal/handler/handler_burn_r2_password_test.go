package handler

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/auth"
	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func newBurnR2PasswordRouter(t *testing.T) (*store.Store, http.Handler) {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { database.Close() })
	st := store.New(database)
	cfg := config.Config{}
	return st, NewRouter(st, &cfg)
}

func mkBurnR2PasswordLink(t *testing.T, st *store.Store, slug, target, password string) int64 {
	t.Helper()
	hash, err := auth.HashPassword(password)
	if err != nil {
		t.Fatalf("HashPassword: %v", err)
	}
	l := &model.Link{
		Slug:         slug,
		URL:          target,
		Enabled:      true,
		Burn:         true,
		PasswordHash: &hash,
	}
	id, err := st.CreateLinkEx(l.Slug, l.URL, l.Title, l.ExpiresAt, l.MaxVisits, l.Burn, l.PurgeAfterBurn)
	if err != nil {
		t.Fatalf("CreateLinkEx(%s): %v", slug, err)
	}
	if err := st.SetLinkPassword(id, hash); err != nil {
		t.Fatalf("SetLinkPassword: %v", err)
	}
	return id
}

func TestBurnR2_PasswordGetPageDoesNotConsume(t *testing.T) {
	st, h := newBurnR2PasswordRouter(t)
	mkBurnR2PasswordLink(t, st, "b2pw1", "https://example.com/w1", "pw12345678")

	rr := doDeep3(t, h, http.MethodGet, "/b2pw1", nil, "")
	if rr.Code != http.StatusOK {
		t.Fatalf("GET password page status = %d, want 200", rr.Code)
	}
	if !strings.Contains(rr.Body.String(), "密码") {
		t.Fatalf("GET password page body missing password prompt: %q", rr.Body.String())
	}

	got, err := st.GetLinkBySlug("b2pw1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if !got.Enabled {
		t.Fatalf("Enabled = false after password page render, want true")
	}
	if got.BurnedAt != nil {
		t.Fatalf("BurnedAt = %v after password page render, want nil", got.BurnedAt)
	}
}

func TestBurnR2_WrongPasswordDoesNotConsume(t *testing.T) {
	st, h := newBurnR2PasswordRouter(t)
	mkBurnR2PasswordLink(t, st, "b2pw1", "https://example.com/w1", "pw12345678")

	body := url.Values{"password": {"wrongpass"}}.Encode()
	rr := doDeep3(t, h, http.MethodPost, "/b2pw1", nil, body)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("POST wrong password status = %d, want 401", rr.Code)
	}
	if !strings.Contains(rr.Body.String(), "密码错误") {
		t.Fatalf("POST wrong password body = %q, want contains 密码错误", rr.Body.String())
	}

	got, err := st.GetLinkBySlug("b2pw1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if !got.Enabled {
		t.Fatalf("Enabled = false after wrong password, want true")
	}
	if got.BurnedAt != nil {
		t.Fatalf("BurnedAt = %v after wrong password, want nil", got.BurnedAt)
	}
	if got.Clicks != 0 {
		t.Fatalf("Clicks = %d after wrong password, want 0", got.Clicks)
	}
}

func TestBurnR2_CorrectPasswordConsumesOnce(t *testing.T) {
	st, h := newBurnR2PasswordRouter(t)
	mkBurnR2PasswordLink(t, st, "b2pw1", "https://example.com/w1", "pw12345678")

	body := url.Values{"password": {"pw12345678"}}.Encode()
	rr := doDeep3(t, h, http.MethodPost, "/b2pw1", nil, body)
	if rr.Code != http.StatusFound {
		t.Fatalf("POST correct password status = %d, want 302", rr.Code)
	}
	if loc := rr.Header().Get("Location"); loc != "https://example.com/w1" {
		t.Fatalf("Location = %q, want https://example.com/w1", loc)
	}

	got, err := st.GetLinkBySlug("b2pw1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.BurnedAt == nil {
		t.Fatalf("BurnedAt = nil after correct password, want non-nil")
	}

	rr2 := doDeep3(t, h, http.MethodPost, "/b2pw1", nil, body)
	if rr2.Code != http.StatusGone {
		t.Fatalf("second POST status = %d, want 410", rr2.Code)
	}
	if !strings.Contains(rr2.Body.String(), "链接已阅销毁") {
		t.Fatalf("second POST body = %q, want contains 链接已阅销毁", rr2.Body.String())
	}
}

func TestBurnR2_BurnedPasswordLinkGet410(t *testing.T) {
	st, h := newBurnR2PasswordRouter(t)
	mkBurnR2PasswordLink(t, st, "b2pw1", "https://example.com/w1", "pw12345678")

	body := url.Values{"password": {"pw12345678"}}.Encode()
	rr := doDeep3(t, h, http.MethodPost, "/b2pw1", nil, body)
	if rr.Code != http.StatusFound {
		t.Fatalf("POST correct password status = %d, want 302", rr.Code)
	}

	rrGet := doDeep3(t, h, http.MethodGet, "/b2pw1", nil, "")
	if rrGet.Code != http.StatusGone {
		t.Fatalf("GET after burn status = %d, want 410", rrGet.Code)
	}
	if !strings.Contains(rrGet.Body.String(), "链接已阅销毁") {
		t.Fatalf("GET after burn body = %q, want contains 链接已阅销毁", rrGet.Body.String())
	}

	_ = httptest.NewRecorder
}