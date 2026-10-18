package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func decodeErrDeep2(t *testing.T, rec *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var m map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &m); err != nil {
		t.Fatalf("unmarshal error body: %v, body=%q", err, rec.Body.String())
	}
	return m
}

func TestMetricsDisabled_Deep2(t *testing.T) {
	st, _ := newDeepTestServer(t)
	h := NewServer(st, config.Config{})

	rec := doJSONServer(t, h, http.MethodGet, "/metrics", nil, nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404, body=%q", rec.Code, rec.Body.String())
	}
	body := decodeErrDeep2(t, rec)
	if body["error"] != "metrics disabled" {
		t.Fatalf("error = %v, want %q", body["error"], "metrics disabled")
	}
}

func TestMetricsNoTokenNoAuth_Deep2(t *testing.T) {
	st, _ := newDeepTestServer(t)
	cfg := config.Config{}
	cfg.Metrics.Enabled = true
	cfg.Metrics.Token = ""
	h := NewServer(st, cfg)

	rec := doJSONServer(t, h, http.MethodGet, "/metrics", nil, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200, body=%q", rec.Code, rec.Body.String())
	}
	body := rec.Body.String()
	if body == "" {
		t.Fatalf("expected non-empty metrics body")
	}
	if !strings.Contains(body, "http_requests_total") && !strings.Contains(body, "# HELP") {
		t.Fatalf("metrics body missing expected markers, body=%q", body)
	}
}

func TestCreateNote_InvalidJSON_Deep2(t *testing.T) {
	st, h := newDeepTestServer(t)
	_ = st

	req := httptest.NewRequest(http.MethodPost, "/api/notes", strings.NewReader("{bad"))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400, body=%q", rec.Code, rec.Body.String())
	}
	body := decodeErrDeep2(t, rec)
	if body["error"] != "invalid json body" {
		t.Fatalf("error = %v, want %q", body["error"], "invalid json body")
	}
}

func TestCreateNote_EmptyTitle_Deep2(t *testing.T) {
	st, h := newDeepTestServer(t)
	_ = st

	rec := doJSONServer(t, h, http.MethodPost, "/api/notes", map[string]any{
		"title": " ",
		"body":  "x",
	}, map[string]string{"Content-Type": "application/json"})

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400, body=%q", rec.Code, rec.Body.String())
	}
	body := decodeErrDeep2(t, rec)
	if body["error"] != "title is required" {
		t.Fatalf("error = %v, want %q", body["error"], "title is required")
	}
}

func TestParseID_Invalid_Deep2(t *testing.T) {
	st, h := newDeepTestServer(t)
	_ = st

	cases := []string{"/api/notes/abc", "/api/notes/0", "/api/notes/-3"}
	for _, target := range cases {
		rec := doJSONServer(t, h, http.MethodGet, target, nil, nil)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("%s: status = %d, want 400, body=%q", target, rec.Code, rec.Body.String())
		}
		body := decodeErrDeep2(t, rec)
		if body["error"] != "invalid id" {
			t.Fatalf("%s: error = %v, want %q", target, body["error"], "invalid id")
		}
	}
}

func TestGetNote_NotFound_Deep2(t *testing.T) {
	st, h := newDeepTestServer(t)
	_ = st

	rec := doJSONServer(t, h, http.MethodGet, "/api/notes/999999", nil, nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404, body=%q", rec.Code, rec.Body.String())
	}
	body := decodeErrDeep2(t, rec)
	if body["error"] != "note not found" {
		t.Fatalf("error = %v, want %q", body["error"], "note not found")
	}
}

func TestDeleteNote_NotFound_Deep2(t *testing.T) {
	_, h := newDeepTestServer(t)
	rec := doJSONServer(t, h, http.MethodDelete, "/api/notes/999999", nil, nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status: got %d want 404 body=%s", rec.Code, rec.Body.String())
	}
}

func TestPutNote_InvalidJSON_Deep2(t *testing.T) {
	_, h := newDeepTestServer(t)

	note := createNote(t, h, store.Note{Title: "put-target"})
	id := note.ID

	req := httptest.NewRequest(http.MethodPut, "/api/notes/"+itoa64(id), strings.NewReader("{bad"))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("invalid json: status = %d, want 400, body=%q", rec.Code, rec.Body.String())
	}
	if b := decodeErrDeep2(t, rec); b["error"] != "invalid json body" {
		t.Fatalf("invalid json: error = %v, want %q", b["error"], "invalid json body")
	}

	rec2 := doJSONServer(t, h, http.MethodPut, "/api/notes/"+itoa64(id), map[string]any{
		"title": " ",
	}, map[string]string{"Content-Type": "application/json"})
	if rec2.Code != http.StatusBadRequest {
		t.Fatalf("empty title: status = %d, want 400, body=%q", rec2.Code, rec2.Body.String())
	}
	if b := decodeErrDeep2(t, rec2); b["error"] != "title is required" {
		t.Fatalf("empty title: error = %v, want %q", b["error"], "title is required")
	}

	rec3 := doJSONServer(t, h, http.MethodPut, "/api/notes/999999", map[string]any{
		"title": "t",
	}, map[string]string{"Content-Type": "application/json"})
	if rec3.Code != http.StatusNotFound {
		t.Fatalf("missing note: status = %d, want 404, body=%q", rec3.Code, rec3.Body.String())
	}
}

func TestSearch_EmptyQuery_Deep2(t *testing.T) {
	st, h := newDeepTestServer(t)
	_ = st

	for _, target := range []string{"/api/search", "/api/search?q=%20%20"} {
		rec := doJSONServer(t, h, http.MethodGet, target, nil, nil)
		if rec.Code != http.StatusOK {
			t.Fatalf("%s: status = %d, want 200, body=%q", target, rec.Code, rec.Body.String())
		}
		var resp struct {
			Query string            `json:"query"`
			Terms []string          `json:"terms"`
			Notes []json.RawMessage `json:"notes"`
			Meta  []json.RawMessage `json:"meta"`
		}
		if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
			t.Fatalf("%s: unmarshal: %v, body=%q", target, err, rec.Body.String())
		}
		if resp.Query != "" {
			t.Fatalf("%s: query = %q, want empty", target, resp.Query)
		}
		if resp.Terms == nil || len(resp.Terms) != 0 {
			t.Fatalf("%s: terms = %v, want empty array", target, resp.Terms)
		}
		if resp.Notes == nil || len(resp.Notes) != 0 {
			t.Fatalf("%s: notes = %v, want empty array", target, resp.Notes)
		}
		if resp.Meta == nil || len(resp.Meta) != 0 {
			t.Fatalf("%s: meta = %v, want empty array", target, resp.Meta)
		}
	}
}

func TestRequestIDEcho_Deep2(t *testing.T) {
	st, h := newDeepTestServer(t)
	_ = st

	req := httptest.NewRequest(http.MethodGet, "/api/health", nil)
	req.Header.Set("X-Request-ID", "rid-echo-42")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200, body=%q", rec.Code, rec.Body.String())
	}
	if got := rec.Header().Get("X-Request-ID"); got != "rid-echo-42" {
		t.Fatalf("X-Request-ID = %q, want %q", got, "rid-echo-42")
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal health body: %v, body=%q", err, rec.Body.String())
	}
	if body["status"] != "ok" {
		t.Fatalf("status field = %v, want %q", body["status"], "ok")
	}
}

func TestErrorBodyCarriesRequestID_Deep2(t *testing.T) {
	st, h := newDeepTestServer(t)
	_ = st

	req := httptest.NewRequest(http.MethodGet, "/api/notes/999999", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404, body=%q", rec.Code, rec.Body.String())
	}
	body := decodeErrDeep2(t, rec)
	rid, ok := body["request_id"].(string)
	if !ok || rid == "" {
		t.Fatalf("request_id = %v, want non-empty string", body["request_id"])
	}
	if hdr := rec.Header().Get("X-Request-ID"); hdr != rid {
		t.Fatalf("response header X-Request-ID = %q, body request_id = %q; want equal", hdr, rid)
	}
}

func TestHealth_Deep2(t *testing.T) {
	st, h := newDeepTestServer(t)
	_ = st

	rec := doJSONServer(t, h, http.MethodGet, "/api/health", nil, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200, body=%q", rec.Code, rec.Body.String())
	}
	ct := rec.Header().Get("Content-Type")
	if !strings.Contains(ct, "application/json") {
		t.Fatalf("Content-Type = %q, want containing application/json", ct)
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal health body: %v, body=%q", err, rec.Body.String())
	}
	if body["status"] != "ok" {
		t.Fatalf("status field = %v, want %q", body["status"], "ok")
	}
}
