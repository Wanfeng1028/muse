package notify

import (
	"context"
	"database/sql"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"sentinel/internal/db"
	"sentinel/internal/store"
)

func newQueueTestStore(t *testing.T) (*sql.DB, *store.Store, int64) {
	t.Helper()
	sqldb, err := db.Open(t.TempDir() + "/q.db")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { sqldb.Close() })
	st := store.New(sqldb)
	mid, err := st.CreateMonitor(store.Monitor{
		Name: "m", Kind: "http", Target: "http://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}
	return sqldb, st, mid
}

func resetDueToPast(t *testing.T, raw *sql.DB, id int64) {
	t.Helper()
	past := time.Now().UTC().Add(-1 * time.Minute).Format(time.RFC3339)
	if _, err := raw.Exec(`UPDATE webhook_deliveries SET next_retry_at =? WHERE id =?`, past, id); err != nil {
		t.Fatalf("reset next_retry_at: %v", err)
	}
}

func TestBackoffForMonotonic(t *testing.T) {
	q := &QueueSender{BaseBackoffSec: 2, MaxAttempts: 5}
	d1 := q.BackoffFor(1)
	d2 := q.BackoffFor(2)
	d3 := q.BackoffFor(3)
	if !(d1 < d2 && d2 < d3) {
		t.Fatalf("expected strictly increasing backoff, got %v %v %v", d1, d2, d3)
	}
	if d1 >= 2*time.Duration(q.BaseBackoffSec)*time.Second {
		t.Fatalf("attempt=1 backoff %v should be < 2*base", d1)
	}
}

func TestProcessDueSuccess(t *testing.T) {
	raw, st, mid := newQueueTestStore(t)
	_ = raw

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
	}))
	defer srv.Close()

	q := &QueueSender{Store: st, MaxAttempts: 3, BaseBackoffSec: 1, TickSec: 1}
	if err := q.EnqueueWebhook(mid, srv.URL, "down", "m", "http://example.com", time.Now().UTC().Format(time.RFC3339), "boom"); err != nil {
		t.Fatalf("EnqueueWebhook: %v", err)
	}

	list, err := st.ListDeliveries("pending", mid, 100)
	if err != nil {
		t.Fatalf("ListDeliveries: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("expected 1 pending, got %d", len(list))
	}
	id := list[0].ID

	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("ProcessDue: %v", err)
	}

	d, err := st.GetDelivery(id)
	if err != nil {
		t.Fatalf("GetDelivery: %v", err)
	}
	if d.Status != "done" {
		t.Fatalf("expected done, got %q", d.Status)
	}
}

func TestProcessDueRetryThenFail(t *testing.T) {
	raw, st, mid := newQueueTestStore(t)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(500)
	}))
	defer srv.Close()

	q := &QueueSender{Store: st, MaxAttempts: 3, BaseBackoffSec: 1, TickSec: 1}
	if err := q.EnqueueWebhook(mid, srv.URL, "down", "m", "http://example.com", time.Now().UTC().Format(time.RFC3339), "boom"); err != nil {
		t.Fatalf("EnqueueWebhook: %v", err)
	}
	list, err := st.ListDeliveries("pending", mid, 100)
	if err != nil {
		t.Fatalf("ListDeliveries: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("expected 1 pending, got %d", len(list))
	}
	id := list[0].ID

	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("ProcessDue 1: %v", err)
	}
	d, err := st.GetDelivery(id)
	if err != nil {
		t.Fatalf("GetDelivery after 1: %v", err)
	}
	if d.Status != "retrying" || d.Attempt != 1 {
		t.Fatalf("expected retrying attempt=1, got status=%q attempt=%d", d.Status, d.Attempt)
	}

	resetDueToPast(t, raw, id)
	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("ProcessDue 2: %v", err)
	}
	d, err = st.GetDelivery(id)
	if err != nil {
		t.Fatalf("GetDelivery after 2: %v", err)
	}
	if d.Status != "retrying" || d.Attempt != 2 {
		t.Fatalf("expected retrying attempt=2, got status=%q attempt=%d", d.Status, d.Attempt)
	}

	resetDueToPast(t, raw, id)
	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("ProcessDue 3: %v", err)
	}
	d, err = st.GetDelivery(id)
	if err != nil {
		t.Fatalf("GetDelivery after 3: %v", err)
	}
	if d.Status != "failed" {
		t.Fatalf("expected failed, got status=%q attempt=%d", d.Status, d.Attempt)
	}
}

func TestEnqueueWebhookIdempotent(t *testing.T) {
	raw, st, mid := newQueueTestStore(t)
	_ = raw

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
	}))
	defer srv.Close()

	q := &QueueSender{Store: st, MaxAttempts: 3, BaseBackoffSec: 1, TickSec: 1}
	at := time.Now().UTC().Format(time.RFC3339)
	if err := q.EnqueueWebhook(mid, srv.URL, "down", "m", "http://example.com", at, "boom"); err != nil {
		t.Fatalf("EnqueueWebhook 1: %v", err)
	}
	if err := q.EnqueueWebhook(mid, srv.URL, "down", "m", "http://example.com", at, "boom"); err != nil {
		t.Fatalf("EnqueueWebhook 2: %v", err)
	}

	counts, err := st.CountDeliveriesByStatus()
	if err != nil {
		t.Fatalf("CountDeliveriesByStatus: %v", err)
	}
	total := 0
	for _, n := range counts {
		total += n
	}
	if total != 1 {
		t.Fatalf("expected 1 total delivery, got %d (%v)", total, counts)
	}
}
