
package handlers

import (
	"net/http"
	"strings"
	"testing"
	"time"
)

func TestDeadLetterAPIFilter(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "dl-api-filter")

	if _, err := st.EnqueueDelivery(mid, "http://example.invalid/dead", "down", `{}`, 8); err != nil {
		t.Fatalf("enqueue dead: %v", err)
	}
	future := time.Now().Add(1 * time.Hour).Format(time.RFC3339)
	claimed, err := st.ClaimDueDeliveries(future, 10)
	if err != nil {
		t.Fatalf("claim: %v", err)
	}
	if len(claimed) != 1 {
		t.Fatalf("want 1 claimed, got %d", len(claimed))
	}
	deadID := claimed[0].ID
	if err := st.MarkDeliveryDead(deadID, "x"); err != nil {
		t.Fatalf("mark dead: %v", err)
	}

	if _, err := st.EnqueueDelivery(mid, "http://example.invalid/failed", "down", `{}`, 8); err != nil {
		t.Fatalf("enqueue failed: %v", err)
	}
	rows, err := st.ListDeliveries("", mid, 10)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	var failedID int64
	for _, r := range rows {
		if r.ID != deadID {
			failedID = r.ID
			break
		}
	}
	if failedID == 0 {
		t.Fatalf("failed row not found")
	}
	if err := st.MarkDeliveryFailed(failedID, "x"); err != nil {
		t.Fatalf("mark failed: %v", err)
	}

	if _, err := st.EnqueueDelivery(mid, "http://example.invalid/pending", "down", `{}`, 8); err != nil {
		t.Fatalf("enqueue pending: %v", err)
	}

	rec, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/alerts/deliveries?status=dead", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("dead: want 200, got %d (%v)", rec.Code, body)
	}
	if got, _ := body["total"].(float64); int(got) != 1 {
		t.Fatalf("dead: want total 1, got %v", body["total"])
	}
	items, _ := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("dead: want 1 item, got %d", len(items))
	}
	first, _ := items[0].(map[string]any)
	if first["status"] != "dead" {
		t.Fatalf("dead: want item status dead, got %v", first["status"])
	}

	rec, body = doJSON(t, srv.Routes(), http.MethodGet, "/api/alerts/deliveries?status=failed", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("failed: want 200, got %d (%v)", rec.Code, body)
	}
	if got, _ := body["total"].(float64); int(got) != 1 {
		t.Fatalf("failed: want total 1, got %v", body["total"])
	}
	items, _ = body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("failed: want 1 item, got %d", len(items))
	}
	first, _ = items[0].(map[string]any)
	if first["status"] != "failed" {
		t.Fatalf("failed: want item status failed, got %v", first["status"])
	}

	rec, body = doJSON(t, srv.Routes(), http.MethodGet, "/api/alerts/deliveries?status=bogus", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("bogus: want 400, got %d (%v)", rec.Code, body)
	}
	msg, _ := body["error"].(string)
	if msg == "" {
		msg, _ = body["message"].(string)
	}
	if !strings.Contains(msg, "dead") {
		t.Fatalf("bogus: want error containing dead, got %q (body %v)", msg, body)
	}
}

func TestDeadLetterManualRetry(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "dl-api-retry")

	if _, err := st.EnqueueDelivery(mid, "http://example.invalid/dead", "down", `{}`, 8); err != nil {
		t.Fatalf("enqueue: %v", err)
	}
	future := time.Now().Add(1 * time.Hour).Format(time.RFC3339)
	claimed, err := st.ClaimDueDeliveries(future, 10)
	if err != nil {
		t.Fatalf("claim: %v", err)
	}
	if len(claimed) != 1 {
		t.Fatalf("want 1 claimed, got %d", len(claimed))
	}
	id := claimed[0].ID
	if err := st.MarkDeliveryDead(id, "x"); err != nil {
		t.Fatalf("mark dead: %v", err)
	}

	rec, body := doJSON(t, srv.Routes(), http.MethodPost, "/api/alerts/deliveries/"+itoa(id)+"/retry", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("retry: want 200, got %d (%v)", rec.Code, body)
	}
	if body["status"] != "pending" {
		t.Fatalf("retry: want status pending, got %v", body["status"])
	}

	rec, body = doJSON(t, srv.Routes(), http.MethodGet, "/api/alerts/deliveries?status=dead", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("dead after retry: want 200, got %d (%v)", rec.Code, body)
	}
	if got, _ := body["total"].(float64); int(got) != 0 {
		t.Fatalf("dead after retry: want total 0, got %v", body["total"])
	}
}
