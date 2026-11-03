package handler

import (
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestExpiryR2_PatchToPastImmediately410(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2ep1", URL: "https://example.com/p1", Enabled: true})
	sid := strconv.FormatInt(id, 10)

	rec := doDeep3(t, h, http.MethodGet, "/b2ep1", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("GET before patch: got %d, want 302", rec.Code)
	}

	req := httptest.NewRequest(http.MethodPatch, "/api/links/"+sid, strings.NewReader(`{"expires_at":"2020-01-01T00:00:00Z"}`))
	req.Header.Set("Content-Type", "application/json")
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("PATCH to past: got %d, want 200; body=%s", rec.Code, rec.Body.String())
	}

	rec = doDeep3(t, h, http.MethodGet, "/b2ep1", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("GET after patch to past: got %d, want 410", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "链接已过期") {
		t.Fatalf("GET after patch to past: body %q does not contain 链接已过期", rec.Body.String())
	}
}

func TestExpiryR2_PatchNullClearsExpiry(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2ep2", URL: "https://example.com/p2", Enabled: true})
	sid := strconv.FormatInt(id, 10)

	req := httptest.NewRequest(http.MethodPatch, "/api/links/"+sid, strings.NewReader(`{"expires_at":"2020-01-01T00:00:00Z"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("PATCH to past: got %d, want 200; body=%s", rec.Code, rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodPatch, "/api/links/"+sid, strings.NewReader(`{"expires_at":null}`))
	req.Header.Set("Content-Type", "application/json")
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("PATCH null: got %d, want 200; body=%s", rec.Code, rec.Body.String())
	}

	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if link.ExpiresAt != nil {
		t.Fatalf("ExpiresAt after PATCH null: got %v, want nil", link.ExpiresAt)
	}

	rec = doDeep3(t, h, http.MethodGet, "/b2ep2", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("GET after PATCH null: got %d, want 302", rec.Code)
	}
}

func TestExpiryR2_PatchEmptyStringClearsExpiry(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-1 * time.Hour)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2ep3", URL: "https://example.com/p3", Enabled: true, ExpiresAt: &past})
	sid := strconv.FormatInt(id, 10)

	rec := doDeep3(t, h, http.MethodGet, "/b2ep3", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("GET before patch: got %d, want 410", rec.Code)
	}

	req := httptest.NewRequest(http.MethodPatch, "/api/links/"+sid, strings.NewReader(`{"expires_at":""}`))
	req.Header.Set("Content-Type", "application/json")
	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("PATCH empty string: got %d, want 200; body=%s", rec.Code, rec.Body.String())
	}

	rec = doDeep3(t, h, http.MethodGet, "/b2ep3", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("GET after PATCH empty string: got %d, want 302", rec.Code)
	}
}

func TestExpiryR2_PatchBadFormat400(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2ep4", URL: "https://example.com/p4", Enabled: true})
	sid := strconv.FormatInt(id, 10)

	req := httptest.NewRequest(http.MethodPatch, "/api/links/"+sid, strings.NewReader(`{"expires_at":"yesterday"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("PATCH bad format: got %d, want 400; body=%s", rec.Code, rec.Body.String())
	}
}
