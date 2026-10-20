package handler

import (
	"net/http"
	"net/url"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/auth"
	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestLimitR2_WrongPasswordDoesNotConsume(t *testing.T) {
	st, h := newDeep3Router(t)
	hash, _ := auth.HashPassword("pw12345678")
	mv := int64(2)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2lp1", URL: "https://example.com/lp1", Enabled: true, MaxVisits: &mv, PasswordHash: &hash})

	rec := doDeep3(t, h, http.MethodPost, "/b2lp1", nil, url.Values{"password": {"wrong"}}.Encode())
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
	link, err := st.GetLinkBySlug("b2lp1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if link.Clicks != 0 {
		t.Fatalf("expected Clicks 0, got %d", link.Clicks)
	}
}

func TestLimitR2_CorrectPasswordConsumes(t *testing.T) {
	st, h := newDeep3Router(t)
	hash, _ := auth.HashPassword("pw12345678")
	mv := int64(2)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2lp2", URL: "https://example.com/lp2", Enabled: true, MaxVisits: &mv, PasswordHash: &hash})

	body := url.Values{"password": {"pw12345678"}}.Encode()
	rec := doDeep3(t, h, http.MethodPost, "/b2lp2", nil, body)
	if rec.Code != http.StatusFound {
		t.Fatalf("first POST expected 302, got %d", rec.Code)
	}
	rec = doDeep3(t, h, http.MethodPost, "/b2lp2", nil, body)
	if rec.Code != http.StatusFound {
		t.Fatalf("second POST expected 302, got %d", rec.Code)
	}
	link, err := st.GetLinkBySlug("b2lp2")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if link.Clicks != 2 {
		t.Fatalf("expected Clicks 2, got %d", link.Clicks)
	}
	rec = doDeep3(t, h, http.MethodPost, "/b2lp2", nil, body)
	if rec.Code != http.StatusGone {
		t.Fatalf("third POST expected 410, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "链接已达访问上限") {
		t.Fatalf("expected body to contain 链接已达访问上限, got %q", rec.Body.String())
	}
}

func TestLimitR2_PasswordPageViewDoesNotConsume(t *testing.T) {
	st, h := newDeep3Router(t)
	hash, _ := auth.HashPassword("pw12345678")
	mv := int64(1)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2lp3", URL: "https://example.com/lp3", Enabled: true, MaxVisits: &mv, PasswordHash: &hash})

	rec := doDeep3(t, h, http.MethodGet, "/b2lp3", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("GET expected 200, got %d", rec.Code)
	}
	link, err := st.GetLinkBySlug("b2lp3")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if link.Clicks != 0 {
		t.Fatalf("expected Clicks 0, got %d", link.Clicks)
	}
	rec = doDeep3(t, h, http.MethodPost, "/b2lp3", nil, url.Values{"password": {"pw12345678"}}.Encode())
	if rec.Code != http.StatusFound {
		t.Fatalf("POST expected 302, got %d", rec.Code)
	}
}

func TestLimitR2_GetPasswordPageOnExhausted200(t *testing.T) {
	st, h := newDeep3Router(t)
	hash, _ := auth.HashPassword("pw12345678")
	mv := int64(1)
	mkLinkDeep3(t, st, &model.Link{Slug: "b2lp4", URL: "https://example.com/lp4", Enabled: true, MaxVisits: &mv, PasswordHash: &hash})

	body := url.Values{"password": {"pw12345678"}}.Encode()
	rec := doDeep3(t, h, http.MethodPost, "/b2lp4", nil, body)
	if rec.Code != http.StatusFound {
		t.Fatalf("first POST expected 302, got %d", rec.Code)
	}
	rec = doDeep3(t, h, http.MethodGet, "/b2lp4", nil, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("GET on exhausted expected 200, got %d", rec.Code)
	}
	rec = doDeep3(t, h, http.MethodPost, "/b2lp4", nil, body)
	if rec.Code != http.StatusGone {
		t.Fatalf("second POST expected 410, got %d", rec.Code)
	}
}