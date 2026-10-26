package handlers

import (
	"net/http"
	"testing"
)

func TestHandleListIncidentsMonitorIDValidationDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()

	rec, body := deep3DoJSON(t, h, http.MethodGet, "/api/incidents?monitor_id=notanumber", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("monitor_id=notanumber: got %d want 400, body=%v", rec.Code, body)
	}

	rec, body = deep3DoJSON(t, h, http.MethodGet, "/api/incidents?monitor_id=-1", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("monitor_id=-1: got %d want 400, body=%v", rec.Code, body)
	}

	id := deep3CreateMonitor(t, h, `{"name":"clamp","kind":"http","target":"https://example.com"}`)
	rec, body = deep3DoJSON(t, h, http.MethodGet, "/api/incidents?monitor_id="+itoa(id), "")
	if rec.Code != http.StatusOK {
		t.Fatalf("monitor_id=%s: got %d want 200, body=%v", itoa(id), rec.Code, body)
	}
	if _, ok := body["items"].([]any); !ok {
		t.Fatalf("expected items array in response, got: %v", body["items"])
	}
}
