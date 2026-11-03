package notify

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/metrics"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

type deep2FTCapture struct {
	mu     sync.Mutex
	events []deep2Event
}

type deep2Event struct {
	Event    string `json:"event"`
	Conflict struct {
		ID       int64  `json:"id"`
		PK       string `json:"pk"`
		Table    string `json:"table"`
		Status   string `json:"status"`
		Resolved string `json:"resolved_at"`
	} `json:"conflict"`
}

func (c *deep2FTCapture) add(ev deep2Event) {
	c.mu.Lock()
	c.events = append(c.events, ev)
	c.mu.Unlock()
}

func (c *deep2FTCapture) snapshot() []deep2Event {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]deep2Event, len(c.events))
	copy(out, c.events)
	return out
}

func (c *deep2FTCapture) count() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.events)
}

func newDeep2CaptureServer(t *testing.T) (*httptest.Server, *deep2FTCapture) {
	t.Helper()
	cap := &deep2FTCapture{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()
		var ev deep2Event
		dec := json.NewDecoder(r.Body)
		if err := dec.Decode(&ev); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		cap.add(ev)
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	return srv, cap
}

func deep2FTOpenStore(t *testing.T) *store.Store {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "deep2.db")
	st, err := store.Open(path)
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("store.Migrate: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })
	return st
}

func deep2WaitForCount(t *testing.T, cap *deep2FTCapture, want int) {
	t.Helper()
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		if cap.count() >= want {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for %d events, got %d", want, cap.count())
}

func deep2AssertNoEvent(t *testing.T, cap *deep2FTCapture, window time.Duration) {
	t.Helper()
	deadline := time.Now().Add(window)
	for time.Now().Before(deadline) {
		if cap.count() > 0 {
			t.Fatalf("unexpected event received: %+v", cap.snapshot())
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func deep2FTNewNotifier(t *testing.T, url string) *Notifier {
	t.Helper()
	cfg := &config.Config{}
	cfg.Notify.ConflictWebhookURL = url
	cfg.Notify.ConflictWebhookSecret = "deep2-secret"
	cfg.Notify.ConflictEvents = []string{"conflict.pending", "conflict.resolved_auto"}
	return FromConfig(cfg, nil)
}

func deep2Record(t *testing.T, st *store.Store, c store.Conflict) {
	t.Helper()
	if _, err := st.RecordConflict(st.DB, c); err != nil {
		t.Fatalf("RecordConflict: %v", err)
	}
}

func deep2RFC3339(t time.Time) string {
	return t.UTC().Format(time.RFC3339)
}

func deep2MetricsDiff(name string, fn func()) float64 {
	before := metrics.Default().Render()
	fn()
	after := metrics.Default().Render()
	return deep2FTMetricValue(after, name) - deep2FTMetricValue(before, name)
}

func deep2FTMetricValue(rendered string, name string) float64 {
	var total float64
	for _, line := range strings.Split(rendered, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}
		if !deep2MetricMatches(fields[0], name) {
			continue
		}
		var v float64
		if _, err := fmt.Sscanf(fields[len(fields)-1], "%g", &v); err != nil {
			continue
		}
		total += v
	}
	return total
}

func deep2MetricMatches(metric string, name string) bool {
	if metric == name {
		return true
	}
	return strings.HasPrefix(metric, name+"{")
}

func TestDeep2FireTable_SinceFiltersOldPending(t *testing.T) {
	srv, cap := newDeep2CaptureServer(t)
	st := deep2FTOpenStore(t)
	n := deep2FTNewNotifier(t, srv.URL)

	now := time.Now().UTC()
	old := now.Add(-2 * time.Hour)
	deep2Record(t, st, store.Conflict{
		TableName: "t_orders",
		PK:        "old1",
		Status:    "pending",
		CreatedAt: deep2RFC3339(old),
	})
	deep2Record(t, st, store.Conflict{
		TableName: "t_orders",
		PK:        "new1",
		Status:    "pending",
		CreatedAt: deep2RFC3339(now),
	})

	since := deep2RFC3339(now.Add(-1 * time.Hour))
	n.FireTableConflicts(st, "t_orders", since)

	deep2WaitForCount(t, cap, 1)
	deep2AssertNoEventExtra(t, cap, 1)

	events := cap.snapshot()
	if len(events) != 1 {
		t.Fatalf("expected exactly 1 event, got %d: %+v", len(events), events)
	}
	if events[0].Event != "conflict.pending" {
		t.Fatalf("expected event conflict.pending, got %q", events[0].Event)
	}
	if events[0].Conflict.PK != "new1" {
		t.Fatalf("expected pk new1, got %q", events[0].Conflict.PK)
	}
}

func deep2AssertNoEventExtra(t *testing.T, cap *deep2FTCapture, want int) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if cap.count() > want {
			t.Fatalf("unexpected extra events: %+v", cap.snapshot())
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func TestDeep2FireTable_ResolvedAutoFallbackCreatedAt(t *testing.T) {
	srv, cap := newDeep2CaptureServer(t)
	st := deep2FTOpenStore(t)
	n := deep2FTNewNotifier(t, srv.URL)

	now := time.Now().UTC()
	deep2Record(t, st, store.Conflict{
		TableName:  "t_items",
		PK:         "r1",
		Status:     "resolved_auto",
		CreatedAt:  deep2RFC3339(now),
		ResolvedAt: "",
	})

	since := deep2RFC3339(now.Add(-1 * time.Hour))
	n.FireTableConflicts(st, "t_items", since)

	deep2WaitForCount(t, cap, 1)
	events := cap.snapshot()
	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}
	if events[0].Event != "conflict.resolved_auto" {
		t.Fatalf("expected event conflict.resolved_auto, got %q", events[0].Event)
	}
	if events[0].Conflict.PK != "r1" {
		t.Fatalf("expected pk r1, got %q", events[0].Conflict.PK)
	}
}

func TestDeep2FireTable_ResolvedAutoResolvedAtFilters(t *testing.T) {
	srv, cap := newDeep2CaptureServer(t)
	st := deep2FTOpenStore(t)
	n := deep2FTNewNotifier(t, srv.URL)

	now := time.Now().UTC()
	oldResolved := now.Add(-2 * time.Hour)
	deep2Record(t, st, store.Conflict{
		TableName:  "t_items",
		PK:         "r2",
		Status:     "resolved_auto",
		CreatedAt:  deep2RFC3339(now),
		ResolvedAt: deep2RFC3339(oldResolved),
	})

	since := deep2RFC3339(now.Add(-1 * time.Hour))
	n.FireTableConflicts(st, "t_items", since)

	deep2AssertNoEvent(t, cap, 2*time.Second)
}

func TestDeep2FireTable_IgnoresOtherStatus(t *testing.T) {
	srv, cap := newDeep2CaptureServer(t)
	st := deep2FTOpenStore(t)
	n := deep2FTNewNotifier(t, srv.URL)

	now := time.Now().UTC()
	deep2Record(t, st, store.Conflict{
		TableName:  "t_items",
		PK:         "x1",
		Status:     "resolved",
		CreatedAt:  deep2RFC3339(now),
		ResolvedAt: deep2RFC3339(now),
	})

	since := deep2RFC3339(now.Add(-1 * time.Hour))
	n.FireTableConflicts(st, "t_items", since)

	deep2AssertNoEvent(t, cap, 2*time.Second)
}

func TestDeep2FireTable_TableNameMismatch(t *testing.T) {
	srv, cap := newDeep2CaptureServer(t)
	st := deep2FTOpenStore(t)
	n := deep2FTNewNotifier(t, srv.URL)

	now := time.Now().UTC()
	deep2Record(t, st, store.Conflict{
		TableName: "table_a",
		PK:        "a1",
		Status:    "pending",
		CreatedAt: deep2RFC3339(now),
	})

	since := deep2RFC3339(now.Add(-1 * time.Hour))
	n.FireTableConflicts(st, "table_b", since)

	deep2AssertNoEvent(t, cap, 2*time.Second)
}

func TestDeep2FireTable_NilStoreNoPanic(t *testing.T) {
	srv, cap := newDeep2CaptureServer(t)
	n := deep2FTNewNotifier(t, srv.URL)

	done := make(chan struct{})
	go func() {
		defer close(done)
		n.FireTableConflicts(nil, "t_orders", "")
	}()

	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatalf("FireTableConflicts with nil store did not return in time")
	}

	if cap.count() != 0 {
		t.Fatalf("expected no events for nil store, got %d", cap.count())
	}
}

func TestDeep2FireTable_DisabledNoQuery(t *testing.T) {
	st := deep2FTOpenStore(t)
	now := time.Now().UTC()
	deep2Record(t, st, store.Conflict{
		TableName: "t_orders",
		PK:        "d1",
		Status:    "pending",
		CreatedAt: deep2RFC3339(now),
	})
	if err := st.Close(); err != nil {
		t.Fatalf("close store: %v", err)
	}

	n := deep2FTNewNotifier(t, "")

	diff := deep2MetricsDiff(MetricDeliveries, func() {
		done := make(chan struct{})
		go func() {
			defer close(done)
			n.FireTableConflicts(st, "t_orders", "")
		}()
		select {
		case <-done:
		case <-time.After(5 * time.Second):
			t.Fatalf("FireTableConflicts did not return in time")
		}
	})

	if diff != 0 {
		t.Fatalf("expected dropped metric diff 0, got %v", diff)
	}
}

func TestDeep2FireAfterCommit_DirectID(t *testing.T) {
	srv, cap := newDeep2CaptureServer(t)
	n := deep2FTNewNotifier(t, srv.URL)

	items := []PendingNotify{
		{
			Event: "conflict.pending",
			Conflict: store.Conflict{
				ID:        99,
				TableName: "t_orders",
				PK:        "direct1",
				Status:    "pending",
				CreatedAt: deep2RFC3339(time.Now().UTC()),
			},
			Table: "t_orders",
			PK:    "direct1",
			Since: "",
		},
	}

	n.FireAfterCommit(nil, items)

	deep2WaitForCount(t, cap, 1)
	events := cap.snapshot()
	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}
	if events[0].Event != "conflict.pending" {
		t.Fatalf("expected event conflict.pending, got %q", events[0].Event)
	}
}

func TestDeep2FireAfterCommit_FallbackByTablePK(t *testing.T) {
	srv, cap := newDeep2CaptureServer(t)
	st := deep2FTOpenStore(t)
	n := deep2FTNewNotifier(t, srv.URL)

	now := time.Now().UTC()
	deep2Record(t, st, store.Conflict{
		TableName:  "t_pk",
		PK:         "pk1",
		Status:     "resolved_auto",
		CreatedAt:  deep2RFC3339(now),
		ResolvedAt: deep2RFC3339(now),
	})
	deep2Record(t, st, store.Conflict{
		TableName:  "t_pk",
		PK:         "pk2",
		Status:     "resolved_auto",
		CreatedAt:  deep2RFC3339(now),
		ResolvedAt: deep2RFC3339(now),
	})

	items := []PendingNotify{
		{
			Event:    "conflict.resolved_auto",
			Conflict: store.Conflict{ID: 0},
			Table:    "t_pk",
			PK:       "pk1",
			Since:    deep2RFC3339(now.Add(-1 * time.Hour)),
		},
	}

	n.FireAfterCommit(st, items)

	deep2WaitForCount(t, cap, 1)
	deep2AssertNoEventExtra(t, cap, 1)

	events := cap.snapshot()
	if len(events) != 1 {
		t.Fatalf("expected exactly 1 event, got %d: %+v", len(events), events)
	}
	if events[0].Event != "conflict.resolved_auto" {
		t.Fatalf("expected event conflict.resolved_auto, got %q", events[0].Event)
	}
	if events[0].Conflict.PK != "pk1" {
		t.Fatalf("expected pk pk1, got %q", events[0].Conflict.PK)
	}
}

func TestDeep2FireAfterCommit_DisabledCountsDropped(t *testing.T) {
	n := deep2FTNewNotifier(t, "")

	items := []PendingNotify{
		{
			Event:    "conflict.pending",
			Conflict: store.Conflict{ID: 1, TableName: "t1", PK: "a"},
		},
		{
			Event:    "conflict.resolved_auto",
			Conflict: store.Conflict{ID: 2, TableName: "t2", PK: "b"},
		},
	}

	diff := deep2MetricsDiff(MetricDeliveries, func() {
		n.FireAfterCommit(nil, items)
	})

	if diff != 2 {
		t.Fatalf("expected dropped metric diff 2, got %v", diff)
	}
}
