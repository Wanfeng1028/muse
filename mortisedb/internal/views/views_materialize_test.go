package views

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
)

func TestRefreshCreatesTableAndRecords(t *testing.T) {
	st := newTestStore(t)

	if err := st.SaveView("v_active", "SELECT \"id\",\"name\" FROM \"users\" WHERE _m_deleted = 0", ""); err != nil {
		t.Fatalf("SaveView: %v", err)
	}

	rows, err := Refresh(st, "v_active")
	if err != nil {
		t.Fatalf("Refresh: %v", err)
	}
	if rows != 2 {
		t.Fatalf("rows = %d, want 2", rows)
	}

	_, got, err := st.Query("SELECT COUNT(*) FROM \"_mv_v_active\"")
	if err != nil {
		t.Fatalf("Query: %v", err)
	}
	if len(got) != 1 || len(got[0]) != 1 {
		t.Fatalf("unexpected count result shape: %#v", got)
	}
	if n, ok := got[0][0].(int64); !ok || n != 2 {
		t.Fatalf("count = %#v, want 2", got[0][0])
	}

	v, err := st.GetView("v_active")
	if err != nil {
		t.Fatalf("GetView: %v", err)
	}
	if v.LastRefreshRows != 2 {
		t.Fatalf("LastRefreshRows = %d, want 2", v.LastRefreshRows)
	}
	if v.LastRefreshAt == "" {
		t.Fatalf("LastRefreshAt is empty")
	}
}

func TestRefreshIsFullRefresh(t *testing.T) {
	st := newTestStore(t)

	if err := st.SaveView("v_all", "SELECT \"id\" FROM \"users\"", ""); err != nil {
		t.Fatalf("SaveView: %v", err)
	}

	rows, err := Refresh(st, "v_all")
	if err != nil {
		t.Fatalf("Refresh #1: %v", err)
	}
	if rows != 3 {
		t.Fatalf("first rows = %d, want 3", rows)
	}

	if _, err := st.DB.Exec("INSERT INTO \"users\" (\"id\",\"name\",\"_m_deleted\") VALUES (4,'赵六',0)"); err != nil {
		t.Fatalf("insert: %v", err)
	}

	rows, err = Refresh(st, "v_all")
	if err != nil {
		t.Fatalf("Refresh #2: %v", err)
	}
	if rows != 4 {
		t.Fatalf("second rows = %d, want 4", rows)
	}

	_, got, err := st.Query("SELECT COUNT(*) FROM \"_mv_v_all\"")
	if err != nil {
		t.Fatalf("Query: %v", err)
	}
	if len(got) != 1 || len(got[0]) != 1 {
		t.Fatalf("unexpected count result shape: %#v", got)
	}
	if n, ok := got[0][0].(int64); !ok || n != 4 {
		t.Fatalf("count = %#v, want 4", got[0][0])
	}
}

func TestRefreshBadSQL(t *testing.T) {
	st := newTestStore(t)

	if err := st.SaveView("v_bad", "SELECT * FROM no_such_table", ""); err != nil {
		t.Fatalf("SaveView: %v", err)
	}

	if _, err := Refresh(st, "v_bad"); err == nil {
		t.Fatalf("expected error from Refresh with bad SQL, got nil")
	}

	_, got, err := st.Query("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='_mv_v_bad'")
	if err != nil {
		t.Fatalf("Query: %v", err)
	}
	if len(got) != 1 || len(got[0]) != 1 {
		t.Fatalf("unexpected count result shape: %#v", got)
	}
	if n, ok := got[0][0].(int64); !ok || n != 0 {
		t.Fatalf("_mv_v_bad exists (count=%#v), want 0", got[0][0])
	}
}

func TestRefreshDueOnSync(t *testing.T) {
	st := newTestStore(t)

	cfg := &config.Config{Views: []config.ViewConfig{{
		Name:        "v_a",
		SQL:         "SELECT 1 AS x",
		Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "on_sync"},
	}}}

	if _, _, _, err := SyncFromConfig(cfg, st); err != nil {
		t.Fatalf("SyncFromConfig: %v", err)
	}

	refreshed, skipped, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue: %v", err)
	}
	if len(refreshed) != 1 || refreshed[0] != "v_a" {
		t.Fatalf("refreshed = %#v, want [v_a]", refreshed)
	}
	if len(skipped) != 0 {
		t.Fatalf("skipped = %#v, want empty", skipped)
	}

	v, err := st.GetView("v_a")
	if err != nil {
		t.Fatalf("GetView: %v", err)
	}
	if !v.Materialized {
		t.Fatalf("Materialized = false, want true")
	}
	if v.RefreshPolicy != "on_sync" {
		t.Fatalf("RefreshPolicy = %q, want on_sync", v.RefreshPolicy)
	}
	if v.LastRefreshRows != 1 {
		t.Fatalf("LastRefreshRows = %d, want 1", v.LastRefreshRows)
	}
}

func TestRefreshDueManualSkipped(t *testing.T) {
	st := newTestStore(t)

	cfg := &config.Config{Views: []config.ViewConfig{{
		Name:        "v_a",
		SQL:         "SELECT 1 AS x",
		Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "manual"},
	}}}

	if _, _, _, err := SyncFromConfig(cfg, st); err != nil {
		t.Fatalf("SyncFromConfig: %v", err)
	}

	refreshed, skipped, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue: %v", err)
	}
	if len(refreshed) != 0 {
		t.Fatalf("refreshed = %#v, want empty", refreshed)
	}
	if len(skipped) != 1 || skipped[0] != "v_a" {
		t.Fatalf("skipped = %#v, want [v_a]", skipped)
	}

	_, got, err := st.Query("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='_mv_v_a'")
	if err != nil {
		t.Fatalf("Query: %v", err)
	}
	if len(got) != 1 || len(got[0]) != 1 {
		t.Fatalf("unexpected count result shape: %#v", got)
	}
	if n, ok := got[0][0].(int64); !ok || n != 0 {
		t.Fatalf("_mv_v_a exists, want absent (count=%#v)", got[0][0])
	}
}

func TestRefreshDueInterval(t *testing.T) {
	st := newTestStore(t)

	cfg := &config.Config{Views: []config.ViewConfig{{
		Name:        "v_a",
		SQL:         "SELECT 1 AS x",
		Materialize: &config.MaterializeConfig{Enabled: true, Refresh: "interval:1h"},
	}}}

	if _, _, _, err := SyncFromConfig(cfg, st); err != nil {
		t.Fatalf("SyncFromConfig: %v", err)
	}

	refreshed, skipped, err := RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue #1: %v", err)
	}
	if len(refreshed) != 1 || refreshed[0] != "v_a" {
		t.Fatalf("first refreshed = %#v, want [v_a]", refreshed)
	}
	if len(skipped) != 0 {
		t.Fatalf("first skipped = %#v, want empty", skipped)
	}

	refreshed, skipped, err = RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue #2: %v", err)
	}
	if len(refreshed) != 0 {
		t.Fatalf("second refreshed = %#v, want empty", refreshed)
	}
	if len(skipped) != 1 || skipped[0] != "v_a" {
		t.Fatalf("second skipped = %#v, want [v_a]", skipped)
	}

	if _, err := st.DB.Exec("UPDATE \"_m_views\" SET \"last_refresh_at\"='2000-01-01T00:00:00Z' WHERE \"name\"='v_a'"); err != nil {
		t.Fatalf("update last_refresh_at: %v", err)
	}

	refreshed, skipped, err = RefreshDue(cfg, st)
	if err != nil {
		t.Fatalf("RefreshDue #3: %v", err)
	}
	if len(refreshed) != 1 || refreshed[0] != "v_a" {
		t.Fatalf("third refreshed = %#v, want [v_a]", refreshed)
	}
	if len(skipped) != 0 {
		t.Fatalf("third skipped = %#v, want empty", skipped)
	}
}

func TestRefreshDueDematerialize(t *testing.T) {
	st := newTestStore(t)

	if err := st.SaveYAMLView("v_old", "SELECT 1 AS x", ""); err != nil {
		t.Fatalf("SaveYAMLView: %v", err)
	}
	if err := st.UpdateViewMaterialize("v_old", true, "on_sync"); err != nil {
		t.Fatalf("UpdateViewMaterialize: %v", err)
	}
	if _, err := st.DB.Exec("CREATE TABLE \"_mv_v_old\" (x INTEGER)"); err != nil {
		t.Fatalf("create _mv_v_old: %v", err)
	}

	cfg := &config.Config{Views: []config.ViewConfig{{
		Name: "v_old",
		SQL:  "SELECT 1 AS x",
	}}}

	if _, _, err := RefreshDue(cfg, st); err != nil {
		t.Fatalf("RefreshDue: %v", err)
	}

	v, err := st.GetView("v_old")
	if err != nil {
		t.Fatalf("GetView: %v", err)
	}
	if v.Materialized {
		t.Fatalf("Materialized = true, want false")
	}

	_, got, err := st.Query("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='_mv_v_old'")
	if err != nil {
		t.Fatalf("Query: %v", err)
	}
	if len(got) != 1 || len(got[0]) != 1 {
		t.Fatalf("unexpected count result shape: %#v", got)
	}
	if n, ok := got[0][0].(int64); !ok || n != 0 {
		t.Fatalf("_mv_v_old exists, want absent (count=%#v)", got[0][0])
	}
}
