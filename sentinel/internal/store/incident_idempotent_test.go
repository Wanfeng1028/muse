package store

import (
	"database/sql"
	"sync"
	"testing"
	"time"

	"sentinel/internal/db"
)

func TestOpenIncident_ConcurrentSameID(t *testing.T) {
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	st := New(d)

	mid, err := st.CreateMonitor(Monitor{
		Name:           "concurrent-down",
		Kind:           "http",
		Target:         "http://127.0.0.1:1/health",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}

	const n = 50
	now := time.Now().UTC().Format(time.RFC3339Nano)

	ids := make([]int64, n)
	createdFlags := make([]bool, n)
	errs := make([]error, n)

	start := make(chan struct{})
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func(idx int) {
			defer wg.Done()
			<-start
			id, created, err := st.OpenIncident(mid, now, "boom")
			ids[idx] = id
			createdFlags[idx] = created
			errs[idx] = err
		}(i)
	}
	close(start)
	wg.Wait()

	for i, err := range errs {
		if err != nil {
			t.Fatalf("OpenIncident call %d returned error: %v", i, err)
		}
	}

	firstID := ids[0]
	if firstID == 0 {
		t.Fatalf("OpenIncident returned zero id on call 0")
	}
	createdCount := 0
	for i := 0; i < n; i++ {
		if ids[i] != firstID {
			t.Fatalf("OpenIncident id mismatch at call %d: got %d want %d", i, ids[i], firstID)
		}
		if createdFlags[i] {
			createdCount++
		}
	}
	if createdCount != 1 {
		t.Fatalf("OpenIncident created=true count: got %d want 1", createdCount)
	}
	if got := n - createdCount; got != 49 {
		t.Fatalf("OpenIncident created=false count: got %d want 49", got)
	}

	incidents, err := st.ListIncidents(mid, 100)
	if err != nil {
		t.Fatalf("ListIncidents failed: %v", err)
	}
	openCount := 0
	for _, inc := range incidents {
		if !inc.EndedAt.Valid {
			openCount++
		}
	}
	if openCount != 1 {
		t.Fatalf("open incidents count: got %d want 1", openCount)
	}
}

func TestOpenIncident_ReopenAfterClose(t *testing.T) {
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	st := New(d)

	mid, err := st.CreateMonitor(Monitor{
		Name:           "reopen-down",
		Kind:           "http",
		Target:         "http://127.0.0.1:1/health",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}

	t1 := time.Now().UTC().Format(time.RFC3339Nano)
	id1, created1, err := st.OpenIncident(mid, t1, "boom1")
	if err != nil {
		t.Fatalf("first OpenIncident failed: %v", err)
	}
	if !created1 {
		t.Fatalf("first OpenIncident created: got false want true")
	}

	t2 := time.Now().UTC().Add(time.Second).Format(time.RFC3339Nano)
	if err := st.CloseOpenIncident(mid, t2, 60); err != nil {
		t.Fatalf("CloseOpenIncident failed: %v", err)
	}

	t3 := time.Now().UTC().Add(2 * time.Second).Format(time.RFC3339Nano)
	id2, created2, err := st.OpenIncident(mid, t3, "boom2")
	if err != nil {
		t.Fatalf("second OpenIncident failed: %v", err)
	}
	if !created2 {
		t.Fatalf("second OpenIncident created: got false want true")
	}
	if id2 == id1 {
		t.Fatalf("second OpenIncident id: got %d want different from %d", id2, id1)
	}

	incidents, err := st.ListIncidents(mid, 100)
	if err != nil {
		t.Fatalf("ListIncidents failed: %v", err)
	}
	if len(incidents) != 2 {
		t.Fatalf("incidents count: got %d want 2", len(incidents))
	}
	openCount := 0
	var openID int64
	for _, inc := range incidents {
		if !inc.EndedAt.Valid {
			openCount++
			openID = inc.ID
		}
	}
	if openCount != 1 {
		t.Fatalf("open incidents count: got %d want 1", openCount)
	}
	if openID != id2 {
		t.Fatalf("open incident id: got %d want %d", openID, id2)
	}
}

func TestOpenIncident_PartialUniqueIndexExists(t *testing.T) {
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}

	var sqlText sql.NullString
	row := d.QueryRow("SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_incidents_open_monitor'")
	if err := row.Scan(&sqlText); err != nil {
		t.Fatalf("query sqlite_master for uq_incidents_open_monitor failed: %v", err)
	}
	if !sqlText.Valid {
		t.Fatalf("uq_incidents_open_monitor index sql is NULL")
	}
	if !contains(sqlText.String, "UNIQUE") {
		t.Fatalf("uq_incidents_open_monitor sql missing UNIQUE: got %q", sqlText.String)
	}
	if !contains(sqlText.String, "WHERE ended_at IS NULL") {
		t.Fatalf("uq_incidents_open_monitor sql missing WHERE ended_at IS NULL: got %q", sqlText.String)
	}
}

func TestCloseOpenIncident_ClosesSingleOpen(t *testing.T) {
	d, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("db.Open failed: %v", err)
	}
	st := New(d)

	mid, err := st.CreateMonitor(Monitor{
		Name:           "close-single",
		Kind:           "http",
		Target:         "http://127.0.0.1:1/health",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     5,
		IntervalSec:    60,
		Enabled:        1,
		TenantID:       1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor failed: %v", err)
	}

	t1 := time.Now().UTC().Format(time.RFC3339Nano)
	if _, created, err := st.OpenIncident(mid, t1, "boom"); err != nil {
		t.Fatalf("OpenIncident failed: %v", err)
	} else if !created {
		t.Fatalf("OpenIncident created: got false want true")
	}

	t2 := time.Now().UTC().Add(time.Second).Format(time.RFC3339Nano)
	if err := st.CloseOpenIncident(mid, t2, 60); err != nil {
		t.Fatalf("CloseOpenIncident failed: %v", err)
	}

	if _, err := st.OpenIncidentStartedAt(mid); err != sql.ErrNoRows {
		t.Fatalf("OpenIncidentStartedAt after close: got err %v want sql.ErrNoRows", err)
	}
}

func contains(s, sub string) bool {
	if len(sub) == 0 {
		return true
	}
	if len(s) < len(sub) {
		return false
	}
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
