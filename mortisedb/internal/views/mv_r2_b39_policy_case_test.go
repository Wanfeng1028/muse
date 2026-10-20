package views

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
)

func TestMvR2B39PolicyCaseSensitive(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t1 (id INTEGER PRIMARY KEY)`)
	st.DB.Exec(`INSERT INTO t1 (id) VALUES (1)`)
	createView(t, st, "v1", `SELECT id FROM t1`)

	cfg := &config.Config{Views: []config.ViewConfig{{Name: "v1", SQL: `SELECT id FROM t1`, Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "Manual"}}}}

	refreshed, skipped, _ := RefreshDue(cfg, st)

	// "Manual" is compared case-sensitively against "manual"; it does not
	// match and falls through to the default branch, so it is skipped.
	// This case sensitivity is the current behavior.
	if len(refreshed) != 0 {
		t.Fatalf("expected refreshed to be empty, got %v", refreshed)
	}
	if len(skipped) != 1 || skipped[0] != "v1" {
		t.Fatalf("expected skipped [v1], got %v", skipped)
	}

	v, err := st.GetView("v1")
	if err != nil {
		t.Fatalf("GetView returned error: %v", err)
	}
	if v.Materialized != true {
		t.Fatalf("expected v1 Materialized to be true, got %v", v.Materialized)
	}
	if v.LastRefreshAt != "" {
		t.Fatalf("expected v1 LastRefreshAt to be empty, got %q", v.LastRefreshAt)
	}
}

func TestMvR2B39PolicyWhitespaceTrimmed(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t2 (id INTEGER PRIMARY KEY)`)
	st.DB.Exec(`INSERT INTO t2 (id) VALUES (1)`)
	createView(t, st, "v2", `SELECT id FROM t2`)

	cfg := &config.Config{Views: []config.ViewConfig{{Name: "v2", SQL: `SELECT id FROM t2`, Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "  on_sync  "}}}}

	refreshed, _, _ := RefreshDue(cfg, st)

	if len(refreshed) != 1 || refreshed[0] != "v2" {
		t.Fatalf("expected refreshed [v2], got %v", refreshed)
	}

	v, err := st.GetView("v2")
	if err != nil {
		t.Fatalf("GetView returned error: %v", err)
	}
	if v.LastRefreshAt == "" {
		t.Fatalf("expected v2 LastRefreshAt to be non-empty after refresh")
	}
}
