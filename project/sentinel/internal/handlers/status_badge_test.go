package handlers

import (
	"net/http/httptest"
	"strings"
	"testing"
)

func TestStatusBadgeUnknownSlugReturnsNotFound(t *testing.T) {
	srv, _ := newTestServer(t)

	req := httptest.NewRequest("GET", "/api/status/unknown-badge-page/badge.svg", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != 404 {
		t.Fatalf("状态码 = %d，期望 404", rec.Code)
	}
}

func TestStatusBadgeMonitorWithoutChecksIsUnknown(t *testing.T) {
	srv, st := newTestServer(t)
	mid := newPublicProbeMonitor(t, st, "badge-probe-without-checks")
	newPublicPage(t, st, "badge-page-without-checks", mid)

	req := httptest.NewRequest("GET", "/api/status/badge-page-without-checks/badge.svg", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != 200 {
		t.Fatalf("状态码 = %d，期望 200", rec.Code)
	}
	if contentType := rec.Header().Get("Content-Type"); !strings.Contains(contentType, "image/svg+xml") {
		t.Fatalf("Content-Type = %q，期望包含 image/svg+xml", contentType)
	}

	body := rec.Body.String()
	for _, want := range []string{"<svg", "unknown", "#9f9f9f"} {
		if !strings.Contains(body, want) {
			t.Errorf("SVG 内容不含 %q，实际内容：%s", want, body)
		}
	}
}

func TestStatusBadgeEmptyPageIsUnknown(t *testing.T) {
	srv, st := newTestServer(t)
	newPublicPage(t, st, "badge-empty-page")

	req := httptest.NewRequest("GET", "/api/status/badge-empty-page/badge.svg", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != 200 {
		t.Fatalf("状态码 = %d，期望 200", rec.Code)
	}
	if contentType := rec.Header().Get("Content-Type"); !strings.Contains(contentType, "image/svg+xml") {
		t.Fatalf("Content-Type = %q，期望包含 image/svg+xml", contentType)
	}

	body := rec.Body.String()
	for _, want := range []string{"<svg", "unknown", "#9f9f9f"} {
		if !strings.Contains(body, want) {
			t.Errorf("SVG 内容不含 %q，实际内容：%s", want, body)
		}
	}
}
