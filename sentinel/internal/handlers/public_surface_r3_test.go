
package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestR2_SetMonitorPublicInvalidValue(t *testing.T) {
	srv, st := newTestServer(t)
	id := newPublicProbeMonitor(t, st, "invalid-value")

	body := `{"is_public":2}`
	req := httptest.NewRequest("PUT", fmt.Sprintf("/api/monitors/%d/public", id), strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer test-token")

	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "is_public 只能为 0 或 1") {
		t.Fatalf("expected body to contain error message, got %q", rec.Body.String())
	}
}

func TestR2_SetMonitorPublicInvalidBody(t *testing.T) {
	srv, st := newTestServer(t)
	id := newPublicProbeMonitor(t, st, "invalid-body")

	body := "{bad json"
	req := httptest.NewRequest("PUT", fmt.Sprintf("/api/monitors/%d/public", id), strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer test-token")

	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "请求体非法") {
		t.Fatalf("expected body to contain error message, got %q", rec.Body.String())
	}
}

func TestR2_SetMonitorPublicUnknownMonitor(t *testing.T) {
	srv, _ := newTestServer(t)

	body := `{"is_public":1}`
	req := httptest.NewRequest("PUT", "/api/monitors/999999/public", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer test-token")

	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "monitor 不存在") {
		t.Fatalf("expected body to contain error message, got %q", rec.Body.String())
	}
}

func TestR2_SetMonitorPublicRoundTrip(t *testing.T) {
	srv, st := newTestServer(t)
	id := newPublicProbeMonitor(t, st, "round-trip")

	body := `{"is_public":1}`
	req := httptest.NewRequest("PUT", fmt.Sprintf("/api/monitors/%d/public", id), strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer test-token")

	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if resp["is_public"] != float64(1) {
		t.Fatalf("expected is_public to be 1, got %v", resp["is_public"])
	}

	body = `{"is_public":0}`
	req = httptest.NewRequest("PUT", fmt.Sprintf("/api/monitors/%d/public", id), strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer test-token")

	rec = httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if resp["is_public"] != float64(0) {
		t.Fatalf("expected is_public to be 0, got %v", resp["is_public"])
	}
}

func TestR2_SetMonitorPublicRequiresAuth(t *testing.T) {
	srv, st := newTestServer(t)
	id := newPublicProbeMonitor(t, st, "requires-auth")

	body := `{"is_public":1}`
	req := httptest.NewRequest("PUT", fmt.Sprintf("/api/monitors/%d/public", id), strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")

	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected status 401, got %d", rec.Code)
	}
}
