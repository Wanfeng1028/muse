package handlers

import (
	"net/http"
	"testing"
)

func TestHandleListChecksLimitInvalidDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()

	id := deep3CreateMonitor(t, h, `{"name":"clamp","kind":"http","target":"https://example.com"}`)
	base := "/api/monitors/" + itoa(id) + "/checks"

	t.Run("limit_not_numeric_rejected", func(t *testing.T) {
		rec, _ := deep3DoJSON(t, h, http.MethodGet, base+"?limit=abc", "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("limit=abc: status = %d, want %d", rec.Code, http.StatusBadRequest)
		}
	})

	t.Run("valid_limit_returns_items", func(t *testing.T) {
		rec, body := deep3DoJSON(t, h, http.MethodGet, base+"?limit=10", "")
		if rec.Code != http.StatusOK {
			t.Fatalf("limit=10: status = %d, want %d", rec.Code, http.StatusOK)
		}
		items, ok := body["items"].([]interface{})
		if !ok {
			t.Fatalf("limit=10: response missing items array, body = %v", body)
		}
		if items == nil {
			t.Fatalf("limit=10: items must be an array, got nil")
		}
	})
}
