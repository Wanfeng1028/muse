package store

import (
	"database/sql"
	"testing"
	"time"

	"sentinel/internal/db"
)

func TestDeliveryMigrationV5Applied(t *testing.T) {
	sqldb, err := db.Open(t.TempDir() + "/v.db")
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	defer sqldb.Close()

	versions, err := db.AppliedVersions(sqldb)
	if err != nil {
		t.Fatalf("AppliedVersions: %v", err)
	}
	found := false
	for _, v := range versions {
		if v == 5 {
			found = true
		}
	}
	if !found {
		t.Fatalf("migration v5 not applied, versions=%v", versions)
	}
}

func TestEnqueueDeliveryAndGet(t *testing.T) {
	st := newTestStore(t)
	mid, err := st.CreateMonitor(Monitor{
		Name: "m1", Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	id, err := st.EnqueueDelivery(mid, "https://example.com/hook", "down", `{"a":1}`, 8)
	if err != nil {
		t.Fatalf("EnqueueDelivery: %v", err)
	}
	if id == 0 {
		t.Fatalf("expected non-zero id")
	}

	d, err := st.GetDelivery(id)
	if err != nil {
		t.Fatalf("GetDelivery: %v", err)
	}
	if d.ID != id || d.MonitorID != mid {
		t.Fatalf("id mismatch: %+v", d)
	}
	if d.URL != "https://example.com/hook" || d.Event != "down" || d.Payload != `{"a":1}` {
		t.Fatalf("field mismatch: %+v", d)
	}
	if d.Status != "pending" {
		t.Fatalf("expected pending, got %q", d.Status)
	}
	if d.Attempt != 0 || d.MaxAttempts != 8 {
		t.Fatalf("attempt/max mismatch: %+v", d)
	}
}

func TestEnqueueDeliveryIdempotent(t *testing.T) {
	st := newTestStore(t)
	mid, err := st.CreateMonitor(Monitor{
		Name: "m1", Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	id1, err := st.EnqueueDelivery(mid, "https://example.com/hook", "down", `{"a":1}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery 1: %v", err)
	}
	id2, err := st.EnqueueDelivery(mid, "https://example.com/hook", "down", `{"a":1}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery 2: %v", err)
	}
	if id1 != id2 {
		t.Fatalf("expected same id for dedup, got %d and %d", id1, id2)
	}

	list, err := st.ListDeliveries("", mid, 100)
	if err != nil {
		t.Fatalf("ListDeliveries: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("expected 1 row, got %d", len(list))
	}

	id3, err := st.EnqueueDelivery(mid, "https://example.com/hook", "down", `{"a":2}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery 3: %v", err)
	}
	if id3 == id1 {
		t.Fatalf("expected new id for different payload")
	}
	list, err = st.ListDeliveries("", mid, 100)
	if err != nil {
		t.Fatalf("ListDeliveries: %v", err)
	}
	if len(list) != 2 {
		t.Fatalf("expected 2 rows, got %d", len(list))
	}
}

func TestClaimDueDeliveriesOnlyDue(t *testing.T) {
	st := newTestStore(t)
	mid, err := st.CreateMonitor(Monitor{
		Name: "m1", Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	past := time.Now().UTC().Add(-1 * time.Minute).Format(time.RFC3339)
	future := time.Now().UTC().Add(1 * time.Hour).Format(time.RFC3339)
	now := time.Now().UTC().Format(time.RFC3339)

	dueID, err := st.EnqueueDelivery(mid, "https://example.com/a", "down", `{"x":1}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery due: %v", err)
	}
	if err := st.MarkDeliveryAttempt(dueID, past, "x"); err != nil {
		t.Fatalf("MarkDeliveryAttempt due: %v", err)
	}

	futureID, err := st.EnqueueDelivery(mid, "https://example.com/b", "down", `{"x":2}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery future: %v", err)
	}
	if err := st.MarkDeliveryAttempt(futureID, future, "x"); err != nil {
		t.Fatalf("MarkDeliveryAttempt future: %v", err)
	}

	claimed, err := st.ClaimDueDeliveries(now, 100)
	if err != nil {
		t.Fatalf("ClaimDueDeliveries: %v", err)
	}
	seen := map[int64]bool{}
	for _, d := range claimed {
		seen[d.ID] = true
	}
	if !seen[dueID] {
		t.Fatalf("expected due row %d to be claimed", dueID)
	}
	if seen[futureID] {
		t.Fatalf("future row %d should not be claimed", futureID)
	}
}

func TestMarkDeliveryAttemptSetsRetrying(t *testing.T) {
	st := newTestStore(t)
	mid, err := st.CreateMonitor(Monitor{
		Name: "m1", Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	id, err := st.EnqueueDelivery(mid, "https://example.com/a", "down", `{"x":1}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery: %v", err)
	}
	next := time.Now().UTC().Add(30 * time.Second).Format(time.RFC3339)
	if err := st.MarkDeliveryAttempt(id, next, "boom"); err != nil {
		t.Fatalf("MarkDeliveryAttempt: %v", err)
	}

	d, err := st.GetDelivery(id)
	if err != nil {
		t.Fatalf("GetDelivery: %v", err)
	}
	if d.Status != "retrying" {
		t.Fatalf("expected retrying, got %q", d.Status)
	}
	if d.Attempt != 1 {
		t.Fatalf("expected attempt=1, got %d", d.Attempt)
	}
	if d.LastError != "boom" {
		t.Fatalf("expected last_error=boom, got %q", d.LastError)
	}
	if !d.NextRetryAt.Valid || d.NextRetryAt.String != next {
		t.Fatalf("expected next_retry_at=%q, got %+v", next, d.NextRetryAt)
	}
}

func TestMarkDeliveryFailed(t *testing.T) {
	st := newTestStore(t)
	mid, err := st.CreateMonitor(Monitor{
		Name: "m1", Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	id, err := st.EnqueueDelivery(mid, "https://example.com/a", "down", `{"x":1}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery: %v", err)
	}
	if err := st.MarkDeliveryFailed(id, "boom"); err != nil {
		t.Fatalf("MarkDeliveryFailed: %v", err)
	}
	d, err := st.GetDelivery(id)
	if err != nil {
		t.Fatalf("GetDelivery: %v", err)
	}
	if d.Status != "failed" {
		t.Fatalf("expected failed, got %q", d.Status)
	}
	if d.LastError != "boom" {
		t.Fatalf("expected last_error=boom, got %q", d.LastError)
	}
}

func TestRetryDelivery(t *testing.T) {
	st := newTestStore(t)
	mid, err := st.CreateMonitor(Monitor{
		Name: "m1", Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	failedID, err := st.EnqueueDelivery(mid, "https://example.com/a", "down", `{"x":1}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery failed: %v", err)
	}
	if err := st.MarkDeliveryFailed(failedID, "boom"); err != nil {
		t.Fatalf("MarkDeliveryFailed: %v", err)
	}
	if err := st.RetryDelivery(failedID); err != nil {
		t.Fatalf("RetryDelivery on failed: %v", err)
	}
	d, err := st.GetDelivery(failedID)
	if err != nil {
		t.Fatalf("GetDelivery: %v", err)
	}
	if d.Status != "pending" {
		t.Fatalf("expected pending, got %q", d.Status)
	}
	if d.Attempt != 0 {
		t.Fatalf("expected attempt=0, got %d", d.Attempt)
	}

	doneID, err := st.EnqueueDelivery(mid, "https://example.com/b", "down", `{"x":2}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery done: %v", err)
	}
	if err := st.MarkDeliveryDone(doneID); err != nil {
		t.Fatalf("MarkDeliveryDone: %v", err)
	}
	if err := st.RetryDelivery(doneID); err == nil {
		t.Fatalf("expected error retrying done row")
	}

	if err := st.RetryDelivery(999999); err != sql.ErrNoRows {
		t.Fatalf("expected sql.ErrNoRows, got %v", err)
	}
}

func TestListDeliveriesFilter(t *testing.T) {
	st := newTestStore(t)
	mid, err := st.CreateMonitor(Monitor{
		Name: "m1", Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	id1, err := st.EnqueueDelivery(mid, "https://example.com/a", "down", `{"x":1}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery 1: %v", err)
	}
	id2, err := st.EnqueueDelivery(mid, "https://example.com/b", "down", `{"x":2}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery 2: %v", err)
	}
	_ = id1
	if err := st.MarkDeliveryFailed(id2, "boom"); err != nil {
		t.Fatalf("MarkDeliveryFailed: %v", err)
	}

	failed, err := st.ListDeliveries("failed", mid, 100)
	if err != nil {
		t.Fatalf("ListDeliveries failed: %v", err)
	}
	if len(failed) != 1 || failed[0].ID != id2 {
		t.Fatalf("expected only failed row, got %+v", failed)
	}

	pending, err := st.ListDeliveries("pending", mid, 100)
	if err != nil {
		t.Fatalf("ListDeliveries pending: %v", err)
	}
	if len(pending) != 1 || pending[0].ID != id1 {
		t.Fatalf("expected only pending row, got %+v", pending)
	}
}

func TestCountDeliveriesByStatus(t *testing.T) {
	st := newTestStore(t)
	mid, err := st.CreateMonitor(Monitor{
		Name: "m1", Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	if _, err := st.EnqueueDelivery(mid, "https://example.com/a", "down", `{"x":1}`, 5); err != nil {
		t.Fatalf("EnqueueDelivery 1: %v", err)
	}
	id2, err := st.EnqueueDelivery(mid, "https://example.com/b", "down", `{"x":2}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery 2: %v", err)
	}
	id3, err := st.EnqueueDelivery(mid, "https://example.com/c", "down", `{"x":3}`, 5)
	if err != nil {
		t.Fatalf("EnqueueDelivery 3: %v", err)
	}
	if err := st.MarkDeliveryFailed(id2, "boom"); err != nil {
		t.Fatalf("MarkDeliveryFailed: %v", err)
	}
	if err := st.MarkDeliveryDone(id3); err != nil {
		t.Fatalf("MarkDeliveryDone: %v", err)
	}

	counts, err := st.CountDeliveriesByStatus()
	if err != nil {
		t.Fatalf("CountDeliveriesByStatus: %v", err)
	}
	if counts["pending"] != 1 {
		t.Fatalf("expected pending=1, got %d", counts["pending"])
	}
	if counts["failed"] != 1 {
		t.Fatalf("expected failed=1, got %d", counts["failed"])
	}
	if counts["done"] != 1 {
		t.Fatalf("expected done=1, got %d", counts["done"])
	}
}
