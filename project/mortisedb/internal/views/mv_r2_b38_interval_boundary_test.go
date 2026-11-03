package views

import (
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
)

func TestMvR2B38IntervalDueAndSkip(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t1 (id INTEGER PRIMARY KEY)`)
	if _, err := st.DB.Exec(`INSERT INTO t1 (id) VALUES (1)`); err != nil {
		t.Fatalf("insert t1: %v", err)
	}
	createView(t, st, "v1", `SELECT id FROM t1`)

	cfg := &config.Config{Views: []config.ViewConfig{{
		Name:        "v1",
		SQL:         `SELECT id FROM t1`,
		Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "interval:1h"},
	}}}

	refreshed, skipped, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue first: %v", err)
	}
	if len(refreshed) != 1 || refreshed[0] != "v1" {
		t.Fatalf("first refreshed = %v, want [v1]", refreshed)
	}
	if len(skipped) != 0 {
		t.Fatalf("first skipped = %v, want empty", skipped)
	}

	if _, err := st.DB.Exec(`UPDATE "_m_views" SET "last_refresh_at"=? WHERE "name"='v1'`, time.Now().Add(-61*time.Minute).UTC().Format(time.RFC3339)); err != nil {
		t.Fatalf("update last_refresh_at (61m): %v", err)
	}
	refreshed2, skipped2, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue second: %v", err)
	}
	if len(refreshed2) != 1 || refreshed2[0] != "v1" {
		t.Fatalf("second refreshed = %v, want [v1]", refreshed2)
	}
	if len(skipped2) != 0 {
		t.Fatalf("second skipped = %v, want empty", skipped2)
	}

	if _, err := st.DB.Exec(`UPDATE "_m_views" SET "last_refresh_at"=? WHERE "name"='v1'`, time.Now().Add(-59*time.Minute).UTC().Format(time.RFC3339)); err != nil {
		t.Fatalf("update last_refresh_at (59m): %v", err)
	}
	refreshed3, skipped3, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue third: %v", err)
	}
	if len(refreshed3) != 0 {
		t.Fatalf("third refreshed = %v, want empty", refreshed3)
	}
	if len(skipped3) != 1 || skipped3[0] != "v1" {
		t.Fatalf("third skipped = %v, want [v1]", skipped3)
	}
}

func TestMvR2B38IntervalZeroAlwaysDue(t *testing.T) {
	st := newMatFileTestStore(t)
	seedTable(t, st, `CREATE TABLE t1 (id INTEGER PRIMARY KEY)`)
	if _, err := st.DB.Exec(`INSERT INTO t1 (id) VALUES (1)`); err != nil {
		t.Fatalf("insert t1: %v", err)
	}
	createView(t, st, "v1", `SELECT id FROM t1`)

	cfg := &config.Config{Views: []config.ViewConfig{{
		Name:        "v1",
		SQL:         `SELECT id FROM t1`,
		Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "interval:1ns"},
	}}}

	refreshed, skipped, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue first: %v", err)
	}
	if len(refreshed) != 1 || refreshed[0] != "v1" {
		t.Fatalf("first refreshed = %v, want [v1]", refreshed)
	}
	if len(skipped) != 0 {
		t.Fatalf("first skipped = %v, want empty", skipped)
	}

	refreshed2, skipped2, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue second: %v", err)
	}
	if len(refreshed2) != 1 || refreshed2[0] != "v1" {
		t.Fatalf("second refreshed = %v, want [v1]", refreshed2)
	}
	if len(skipped2) != 0 {
		t.Fatalf("second skipped = %v, want empty", skipped2)
	}
}
