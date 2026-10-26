package handlers

import (
	"net/http"
	"testing"
)

func TestHandleStatsDaysValidationDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()
	id := deep3CreateMonitor(t, h, `{"name":"stats","kind":"http","target":"https://example.com"}`)
	base := "/api/monitors/" + itoa(id) + "/stats"
	t.Run("days_not_numeric_rejected", func(t *testing.T) {
		rec, _ := deep3DoJSON(t, h, http.MethodGet, base+"?days=abc", "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("days=abc: status = %d, want %d", rec.Code, http.StatusBadRequest)
		}
	})
	t.Run("valid_days_returns_stats", func(t *testing.T) {
		rec, body := deep3DoJSON(t, h, http.MethodGet, base+"?days=10", "")
		if rec.Code != http.StatusOK {
			t.Fatalf("days=10: status = %d, want %d", rec.Code, http.StatusOK)
		}
		for _, key := range []string{"uptime_pct", "avg_latency_ms", "total_checks", "down_incidents"} {
			if _, ok := body[key]; !ok {
				t.Fatalf("days=10: missing %s in %v", key, body)
			}
		}
	})
}
