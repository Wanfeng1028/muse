package handlers

import (
	"net/http"
	"testing"
	"time"

	"sentinel/internal/store"
)

func seedStatusFilterIncidents(t *testing.T, st *store.Store) (int64, int64, int64) {
	t.Helper()

	mAID, err := st.CreateMonitor(store.Monitor{Name: "A", Kind: "http", Target: "http://127.0.0.1:1/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}
	base := time.Date(2026, 10, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < 3; i++ {
		sa := base.Add(time.Duration(i) * time.Minute)
		ea := sa.Add(30 * time.Second)
		if _, _, err := st.OpenIncident(mAID, sa.Format(time.RFC3339Nano), "err"); err != nil {
			t.Fatal(err)
		}
		if _, err := st.CloseOpenIncident(mAID, ea.Format(time.RFC3339Nano), 60); err != nil {
			t.Fatal(err)
		}
	}

	mBID, err := st.CreateMonitor(store.Monitor{Name: "B", Kind: "http", Target: "http://127.0.0.1:2/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}
	if _, _, err := st.OpenIncident(mBID, time.Now().Format(time.RFC3339Nano), "err"); err != nil {
		t.Fatal(err)
	}

	mCID, err := st.CreateMonitor(store.Monitor{Name: "C", Kind: "http", Target: "http://127.0.0.1:3/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}
	if _, _, err := st.OpenIncident(mCID, time.Now().Format(time.RFC3339Nano), "err"); err != nil {
		t.Fatal(err)
	}

	return mAID, mBID, mCID
}

func TestHandleListIncidentsStatusFilterOpen(t *testing.T) {
	srv, st := newTestServer(t)
	seedStatusFilterIncidents(t, st)

	w, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?status=open", "")
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	if body["total"].(float64) != 2 {
		t.Fatalf("expected total 2, got %v", body["total"])
	}
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("expected 2 items, got %d", len(items))
	}
	for _, item := range items {
		m := item.(map[string]any)
		if m["ended_at"] != nil {
			t.Fatalf("expected ended_at nil, got %v", m["ended_at"])
		}
	}
}

func TestHandleListIncidentsStatusFilterClosed(t *testing.T) {
	srv, st := newTestServer(t)
	seedStatusFilterIncidents(t, st)

	w, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?status=closed", "")
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	if body["total"].(float64) != 3 {
		t.Fatalf("expected total 3, got %v", body["total"])
	}
	items := body["items"].([]any)
	if len(items) != 3 {
		t.Fatalf("expected 3 items, got %d", len(items))
	}
	for _, item := range items {
		m := item.(map[string]any)
		if m["ended_at"] == nil {
			t.Fatal("expected ended_at non-nil")
		}
	}
}

func TestHandleListIncidentsStatusFilterAll(t *testing.T) {
	srv, st := newTestServer(t)
	seedStatusFilterIncidents(t, st)

	w, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents", "")
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	if body["total"].(float64) != 5 {
		t.Fatalf("expected total 5, got %v", body["total"])
	}
}

func TestHandleListIncidentsStatusFilterInvalid(t *testing.T) {
	srv, _ := newTestServer(t)

	w, _ := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?status=bogus", "")
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestHandleListIncidentsStatusFilterClosedPaged(t *testing.T) {
	srv, st := newTestServer(t)
	seedStatusFilterIncidents(t, st)

	mDID, err := st.CreateMonitor(store.Monitor{Name: "D", Kind: "http", Target: "http://127.0.0.1:4/health", Method: "GET", ExpectedStatus: 200, TimeoutSec: 5, IntervalSec: 60, Enabled: 1, TenantID: 1})
	if err != nil {
		t.Fatalf("create monitor: %v", err)
	}
	sa := time.Date(2026, 10, 1, 0, 10, 0, 0, time.UTC)
	ea := sa.Add(30 * time.Second)
	if _, _, err := st.OpenIncident(mDID, sa.Format(time.RFC3339Nano), "err"); err != nil {
		t.Fatal(err)
	}
	if _, err := st.CloseOpenIncident(mDID, ea.Format(time.RFC3339Nano), 60); err != nil {
		t.Fatal(err)
	}

	w, body := doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?status=closed&page=1&page_size=1", "")
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	if body["total"].(float64) != 4 {
		t.Fatalf("expected total 4, got %v", body["total"])
	}
	items1 := body["items"].([]any)
	if len(items1) != 1 {
		t.Fatalf("expected 1 item on page 1, got %d", len(items1))
	}
	page1StartedAt := items1[0].(map[string]any)["started_at"]

	w, body = doJSON(t, srv.Routes(), http.MethodGet, "/api/incidents?status=closed&page=2&page_size=1", "")
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	if body["total"].(float64) != 4 {
		t.Fatalf("expected total 4, got %v", body["total"])
	}
	items2 := body["items"].([]any)
	if len(items2) != 1 {
		t.Fatalf("expected 1 item on page 2, got %d", len(items2))
	}
	page2StartedAt := items2[0].(map[string]any)["started_at"]
	if page1StartedAt == page2StartedAt {
		t.Fatalf("page 1 and page 2 started_at should differ, got %v and %v", page1StartedAt, page2StartedAt)
	}
}
