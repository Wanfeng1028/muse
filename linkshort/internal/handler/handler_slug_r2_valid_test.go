package handler

import (
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSlugR2_SlugWithSpace400(t *testing.T) {
	_, h := newDeep3Router(t)
	body := `{"url":"https://example.com/s1","slug":"has space"}`
	req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != 400 {
		t.Fatalf("expected 400, got %d, body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "slug 不合规") {
		t.Fatalf("expected body to contain %q, got %s", "slug 不合规", rr.Body.String())
	}
}

func TestSlugR2_SlugWithSlash400(t *testing.T) {
	_, h := newDeep3Router(t)
	body := `{"url":"https://example.com/s2","slug":"a/b"}`
	req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != 400 {
		t.Fatalf("expected 400, got %d, body=%s", rr.Code, rr.Body.String())
	}
}

func TestSlugR2_SlugTooLong400(t *testing.T) {
	_, h := newDeep3Router(t)
	body := `{"url":"https://example.com/s3","slug":"` + strings.Repeat("a", 65) + `"}`
	req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != 400 {
		t.Fatalf("expected 400, got %d, body=%s", rr.Code, rr.Body.String())
	}
}

func TestSlugR2_SlugUnicode400(t *testing.T) {
	_, h := newDeep3Router(t)
	body := `{"url":"https://example.com/s4","slug":"中文slug"}`
	req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != 400 {
		t.Fatalf("expected 400, got %d, body=%s", rr.Code, rr.Body.String())
	}
}

func TestSlugR2_SlugBoundary64OK(t *testing.T) {
	_, h := newDeep3Router(t)
	body := `{"url":"https://example.com/s5","slug":"` + strings.Repeat("a", 64) + `"}`
	req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != 201 {
		t.Fatalf("expected 201, got %d, body=%s", rr.Code, rr.Body.String())
	}
}

func TestSlugR2_SlugHyphenUnderscoreOK(t *testing.T) {
	_, h := newDeep3Router(t)
	body := `{"url":"https://example.com/s6","slug":"a-B_c9"}`
	req := httptest.NewRequest("POST", "/api/links", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != 201 {
		t.Fatalf("expected 201, got %d, body=%s", rr.Code, rr.Body.String())
	}
}
