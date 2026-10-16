package handlers

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"sentinel/internal/store"
)

func mkMonitor(t *testing.T, st *store.Store, name string) int64 {
	t.Helper()
	mid, err := st.CreateMonitor(store.Monitor{
		Name: name, Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	return mid
}

func TestListDeliveriesEndpoint(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "m1")

	base := time.Now().UTC()
	pendingID, err := st.EnqueueDelivery(mid, "https://example.com/a", "down", `{"at":"`+base.Format(time.RFC3339)+`"}`, 8)
	if err != nil {
		t.Fatalf("EnqueueDelivery pending: %v", err)
	}

	retryID, err := st.EnqueueDelivery(mid, "https://example.com/b", "down", `{"at":"`+base.Add(time.Second).Format(time.RFC3339)+`"}`, 8)
	if err != nil {
		t.Fatalf("EnqueueDelivery retrying: %v", err)
	}
	if err := st.MarkDeliveryAttempt(retryID, base.Add(-1*time.Minute).Format(time.RFC3339), "boom"); err != nil {
		t.Fatalf("MarkDeliveryAttempt: %v", err)
	}

	failedID, err := st.EnqueueDelivery(mid, "https://example.com/c", "down", `{"at":"`+base.Add(2*time.Second).Format(time.RFC3339)+`"}`, 8)
	if err != nil {
		t.Fatalf("EnqueueDelivery failed: %v", err)
	}
	if err := st.MarkDeliveryFailed(failedID, "boom"); err != nil {
		t.Fatalf("MarkDeliveryFailed: %v", err)
	}

	_ = pendingID

	rec, body := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%v", rec.Code, body)
	}
	if int(body["total"].(float64)) != 3 {
		t.Fatalf("expected total=3, got %v", body["total"])
	}

	rec, body = doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries?status=failed", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%v", rec.Code, body)
	}
	items, _ := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected 1 failed item, got %d", len(items))
	}
	first, _ := items[0].(map[string]any)
	if first == nil || first["status"] != "failed" {
		t.Fatalf("expected failed item, got %v", first)
	}
	if int(body["total"].(float64)) != 1 {
		t.Fatalf("expected total=1, got %v", body["total"])
	}

	rec, _ = doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries?status=bogus", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid status, got %d", rec.Code)
	}

	rec, body = doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries?limit=1", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%v", rec.Code, body)
	}
	items, _ = body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected 1 item with limit=1, got %d", len(items))
	}
}

func TestRetryDeliveryEndpoint(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "m1")

	base := time.Now().UTC()
	failedID, err := st.EnqueueDelivery(mid, "https://example.com/a", "down", `{"at":"`+base.Format(time.RFC3339)+`"}`, 8)
	if err != nil {
		t.Fatalf("EnqueueDelivery failed: %v", err)
	}
	if err := st.MarkDeliveryFailed(failedID, "boom"); err != nil {
		t.Fatalf("MarkDeliveryFailed: %v", err)
	}

	rec, _ := doJSON(t, srv.Routes(), "POST", "/api/alerts/deliveries/"+itoa(failedID)+"/retry", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 retry, got %d", rec.Code)
	}
	d, err := st.GetDelivery(failedID)
	if err != nil {
		t.Fatalf("GetDelivery: %v", err)
	}
	if d.Status != "pending" {
		t.Fatalf("expected pending after retry, got %q", d.Status)
	}

	doneID, err := st.EnqueueDelivery(mid, "https://example.com/b", "down", `{"at":"`+base.Add(time.Second).Format(time.RFC3339)+`"}`, 8)
	if err != nil {
		t.Fatalf("EnqueueDelivery done: %v", err)
	}
	if err := st.MarkDeliveryDone(doneID); err != nil {
		t.Fatalf("MarkDeliveryDone: %v", err)
	}
	rec, _ = doJSON(t, srv.Routes(), "POST", "/api/alerts/deliveries/"+itoa(doneID)+"/retry", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 retry done, got %d", rec.Code)
	}

	rec, _ = doJSON(t, srv.Routes(), "POST", "/api/alerts/deliveries/999999/retry", "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 retry missing, got %d", rec.Code)
	}
}

func TestListDeliveriesUnauthorized(t *testing.T) {
	srv, _ := newTestServer(t)
	req := httptest.NewRequest("GET", "/api/alerts/deliveries", nil)
	rec := httptest.NewRecorder()
	srv.Routes().ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
}
