package handlers

import (
	"net/http"
	"testing"
	"time"
)

func TestListDeliveriesDeepMonitorIDFilter(t *testing.T) {
	srv, st := newTestServer(t)
	midA := mkMonitor(t, st, "alpha")
	midB := mkMonitor(t, st, "beta")

	base := time.Now().UTC()
	if _, err := st.EnqueueDelivery(midA, "https://example.com/a", "down", `{"at":"`+base.Format(time.RFC3339)+`"}`, 8); err != nil {
		t.Fatalf("enqueue a: %v", err)
	}
	if _, err := st.EnqueueDelivery(midB, "https://example.com/b", "up", `{"at":"`+base.Add(time.Second).Format(time.RFC3339)+`"}`, 8); err != nil {
		t.Fatalf("enqueue b: %v", err)
	}

	rec, body := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries?monitor_id="+itoa(midA), "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%v", rec.Code, body)
	}
	items, _ := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected 1 item for monitor filter, got %d", len(items))
	}
	first, _ := items[0].(map[string]any)
	if first == nil {
		t.Fatalf("nil item")
	}
	if int64(first["monitor_id"].(float64)) != midA {
		t.Fatalf("expected monitor_id=%d got %v", midA, first["monitor_id"])
	}
	if first["monitor_name"] != "alpha" {
		t.Fatalf("expected monitor_name=alpha got %v", first["monitor_name"])
	}
}

func TestListDeliveriesDeepMonitorIDInvalid(t *testing.T) {
	srv, _ := newTestServer(t)
	cases := []string{"abc", "-1", "1.5"}
	for _, c := range cases {
		rec, _ := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries?monitor_id="+c, "")
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400 for monitor_id=%q, got %d", c, rec.Code)
		}
	}
}

func TestListDeliveriesDeepMonitorIDZeroAllowed(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "zero")
	base := time.Now().UTC()
	if _, err := st.EnqueueDelivery(mid, "https://example.com/z", "down", `{"at":"`+base.Format(time.RFC3339)+`"}`, 8); err != nil {
		t.Fatalf("enqueue: %v", err)
	}
	rec, body := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries?monitor_id=0", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for monitor_id=0, got %d body=%v", rec.Code, body)
	}
	items, _ := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected monitor_id=0 to mean no filter, got %d", len(items))
	}
}

func TestListDeliveriesDeepLimitInvalid(t *testing.T) {
	srv, _ := newTestServer(t)
	rec, _ := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries?limit=xyz", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for limit=xyz, got %d", rec.Code)
	}
}

func TestListDeliveriesDeepLimitClampLow(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "clamp-low")
	base := time.Now().UTC()
	for i := 0; i < 3; i++ {
		if _, err := st.EnqueueDelivery(mid, "https://example.com/x", "down", `{"at":"`+base.Add(time.Duration(i)*time.Second).Format(time.RFC3339)+`"}`, 8); err != nil {
			t.Fatalf("enqueue %d: %v", i, err)
		}
	}
	rec, body := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries?limit=0", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%v", rec.Code, body)
	}
	items, _ := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected limit=0 clamped to 1, got %d", len(items))
	}
}

func TestListDeliveriesDeepLimitClampHigh(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "clamp-high")
	base := time.Now().UTC()
	if _, err := st.EnqueueDelivery(mid, "https://example.com/h", "down", `{"at":"`+base.Format(time.RFC3339)+`"}`, 8); err != nil {
		t.Fatalf("enqueue: %v", err)
	}
	rec, body := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries?limit=99999", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%v", rec.Code, body)
	}
	items, _ := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected high limit clamped, got %d items", len(items))
	}
}

func TestListDeliveriesDeepStatusWhitespaceTrimmed(t *testing.T) {
	srv, _ := newTestServer(t)
	rec, _ := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries?status=%20bogus%20", "")
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for trimmed bogus status, got %d", rec.Code)
	}
}

func TestListDeliveriesDeepEmptyItemsShape(t *testing.T) {
	srv, _ := newTestServer(t)
	rec, body := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%v", rec.Code, body)
	}
	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("items should be an array, got %T", body["items"])
	}
	if len(items) != 0 {
		t.Fatalf("expected empty items, got %d", len(items))
	}
	if int(body["total"].(float64)) != 0 {
		t.Fatalf("expected total=0, got %v", body["total"])
	}
}

func TestListDeliveriesDeepMonitorNameFallback(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "")
	base := time.Now().UTC()
	if _, err := st.EnqueueDelivery(mid, "https://example.com/fallback", "down", `{"at":"`+base.Format(time.RFC3339)+`"}`, 8); err != nil {
		t.Fatalf("enqueue: %v", err)
	}
	rec, body := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%v", rec.Code, body)
	}
	items, _ := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected 1 item, got %d", len(items))
	}
	first, _ := items[0].(map[string]any)
	got, _ := first["monitor_name"].(string)
	if got != "#"+itoa(mid) {
		t.Fatalf("expected fallback name #%d, got %q", mid, got)
	}
}

func TestListDeliveriesDeepNextRetryAtNil(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "nra")
	base := time.Now().UTC()
	if _, err := st.EnqueueDelivery(mid, "https://example.com/nra", "down", `{"at":"`+base.Format(time.RFC3339)+`"}`, 8); err != nil {
		t.Fatalf("enqueue: %v", err)
	}
	rec, body := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%v", rec.Code, body)
	}
	items, _ := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected 1 item, got %d", len(items))
	}
	first, _ := items[0].(map[string]any)
	if first["next_retry_at"] == nil {
		t.Fatalf("expected next_retry_at non-nil, got nil")
	}
	if _, ok := first["next_retry_at"].(string); !ok {
		t.Fatalf("expected next_retry_at string, got %T", first["next_retry_at"])
	}
}

func TestRetryDeliveryDeepInvalidID(t *testing.T) {
	srv, _ := newTestServer(t)
	for _, bad := range []string{"abc", "-1", "0", "9999999999999999999999"} {
		rec, _ := doJSON(t, srv.Routes(), "POST", "/api/alerts/deliveries/"+bad+"/retry", "")
		if rec.Code != http.StatusBadRequest && rec.Code != http.StatusNotFound {
			t.Fatalf("expected 400/404 for id=%q, got %d", bad, rec.Code)
		}
	}
}

func TestRetryDeliveryDeepResponseShape(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "shape")
	base := time.Now().UTC()
	failedID, err := st.EnqueueDelivery(mid, "https://example.com/shape", "down", `{"at":"`+base.Format(time.RFC3339)+`"}`, 8)
	if err != nil {
		t.Fatalf("enqueue: %v", err)
	}
	if err := st.MarkDeliveryFailed(failedID, "boom"); err != nil {
		t.Fatalf("mark failed: %v", err)
	}
	rec, body := doJSON(t, srv.Routes(), "POST", "/api/alerts/deliveries/"+itoa(failedID)+"/retry", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%v", rec.Code, body)
	}
	if int64(body["id"].(float64)) != failedID {
		t.Fatalf("expected id=%d got %v", failedID, body["id"])
	}
	if body["status"] != "pending" {
		t.Fatalf("expected status=pending, got %v", body["status"])
	}
	if body["last_error"] != "" {
		t.Fatalf("expected last_error cleared to empty string, got %v", body["last_error"])
	}
	if int64(body["monitor_id"].(float64)) != mid {
		t.Fatalf("expected monitor_id=%d got %v", mid, body["monitor_id"])
	}
}

func TestRetryDeliveryDeepAttemptReset(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "attempt-reset")
	base := time.Now().UTC()
	id, err := st.EnqueueDelivery(mid, "https://example.com/ar", "down", `{"at":"`+base.Format(time.RFC3339)+`"}`, 8)
	if err != nil {
		t.Fatalf("enqueue: %v", err)
	}
	if err := st.MarkDeliveryAttempt(id, base.Format(time.RFC3339), "oops"); err != nil {
		t.Fatalf("mark attempt: %v", err)
	}
	rec, _ := doJSON(t, srv.Routes(), "POST", "/api/alerts/deliveries/"+itoa(id)+"/retry", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 retry, got %d", rec.Code)
	}
	d, err := st.GetDelivery(id)
	if err != nil {
		t.Fatalf("GetDelivery: %v", err)
	}
	if d.Attempt != 0 {
		t.Fatalf("expected attempt reset to 0, got %d", d.Attempt)
	}
}

func TestRetryDeliveryDeepRetryingState(t *testing.T) {
	srv, st := newTestServer(t)
	mid := mkMonitor(t, st, "retrying")
	base := time.Now().UTC()
	id, err := st.EnqueueDelivery(mid, "https://example.com/r", "down", `{"at":"`+base.Format(time.RFC3339)+`"}`, 8)
	if err != nil {
		t.Fatalf("enqueue: %v", err)
	}
	if err := st.MarkDeliveryAttempt(id, base.Format(time.RFC3339), "boom"); err != nil {
		t.Fatalf("mark attempt: %v", err)
	}
	rec, body := doJSON(t, srv.Routes(), "POST", "/api/alerts/deliveries/"+itoa(id)+"/retry", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 retry retrying, got %d body=%v", rec.Code, body)
	}
	if body["status"] != "pending" {
		t.Fatalf("expected pending after retry, got %v", body["status"])
	}
}

func TestListDeliveriesDeepCombinedFilters(t *testing.T) {
	srv, st := newTestServer(t)
	midA := mkMonitor(t, st, "combo-a")
	midB := mkMonitor(t, st, "combo-b")
	base := time.Now().UTC()

	idA1, err := st.EnqueueDelivery(midA, "https://example.com/a1", "down", `{"at":"`+base.Format(time.RFC3339)+`"}`, 8)
	if err != nil {
		t.Fatalf("enqueue a1: %v", err)
	}
	if err := st.MarkDeliveryFailed(idA1, "x"); err != nil {
		t.Fatalf("mark failed a1: %v", err)
	}
	if _, err := st.EnqueueDelivery(midA, "https://example.com/a2", "down", `{"at":"`+base.Add(time.Second).Format(time.RFC3339)+`"}`, 8); err != nil {
		t.Fatalf("enqueue a2: %v", err)
	}
	idB1, err := st.EnqueueDelivery(midB, "https://example.com/b1", "down", `{"at":"`+base.Add(2*time.Second).Format(time.RFC3339)+`"}`, 8)
	if err != nil {
		t.Fatalf("enqueue b1: %v", err)
	}
	if err := st.MarkDeliveryFailed(idB1, "y"); err != nil {
		t.Fatalf("mark failed b1: %v", err)
	}

	rec, body := doJSON(t, srv.Routes(), "GET", "/api/alerts/deliveries?status=failed&monitor_id="+itoa(midA)+"&limit=10", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%v", rec.Code, body)
	}
	items, _ := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected 1 item, got %d", len(items))
	}
	first, _ := items[0].(map[string]any)
	if int64(first["id"].(float64)) != idA1 {
		t.Fatalf("expected id=%d got %v", idA1, first["id"])
	}
}
