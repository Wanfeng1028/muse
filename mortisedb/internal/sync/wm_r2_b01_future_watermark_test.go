package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B01FuturePresetBlocksAllThenAdvances(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	if err := st.SetWatermark("s1", "t", "updated_at", "2027-01-01T00:00:00Z"); err != nil {
		t.Fatalf("preset watermark: %v", err)
	}

	dir := t.TempDir()
	csvPath := writeCSVStr(t, dir, "data.csv",
		"id,updated_at\n"+
			"1,2026-10-20 09:00:00\n"+
			"2,2026-10-20 10:00:00\n"+
			"3,2026-10-20 11:00:00\n")

	cfg := config.SourceConfig{Type: "csv", Name: "s1", Path: csvPath, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, cfg, "job-future-block")
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 0 {
		t.Fatalf("expected Inserted==0 with future preset, got %d", ts.Inserted)
	}
	if ts.Updated != 0 {
		t.Fatalf("expected Updated==0 with future preset, got %d", ts.Updated)
	}
	if ts.Skipped != 0 {
		t.Fatalf("expected Skipped==0 with future preset, got %d", ts.Skipped)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark: %v", err)
	}
	if wm != "2027-01-01T00:00:00Z" {
		t.Fatalf("expected watermark unchanged 2027-01-01T00:00:00Z, got %q", wm)
	}

	csvPath2 := writeCSVStr(t, dir, "data2.csv",
		"id,updated_at\n"+
			"1,2026-10-20 09:00:00\n"+
			"2,2026-10-20 10:00:00\n"+
			"3,2026-10-20 11:00:00\n"+
			"4,2027-06-01T00:00:00Z\n")

	cfg2 := config.SourceConfig{Type: "csv", Name: "s1", Path: csvPath2, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats2 := runSync(t, st, cfg2, "job-future-advance")
	ts2 := tableStat(t, stats2, "t")
	if ts2.Inserted != 1 {
		t.Fatalf("expected Inserted==1 after appending future row, got %d", ts2.Inserted)
	}

	wm2, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark after advance: %v", err)
	}
	if wm2 != "2027-06-01T00:00:00Z" {
		t.Fatalf("expected watermark advanced to 2027-06-01T00:00:00Z, got %q", wm2)
	}
}

func TestWmR2B01FuturePresetEmptyBatchKeepsWatermark(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	if err := st.SetWatermark("s1", "t", "updated_at", "2027-01-01T00:00:00Z"); err != nil {
		t.Fatalf("preset watermark: %v", err)
	}

	dir := t.TempDir()
	csvPath := writeCSVStr(t, dir, "empty.csv", "id,updated_at\n")

	cfg := config.SourceConfig{Type: "csv", Name: "s1", Path: csvPath, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, cfg, "job-future-empty")
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 0 {
		t.Fatalf("expected Inserted==0 on empty batch, got %d", ts.Inserted)
	}
	if ts.Updated != 0 {
		t.Fatalf("expected Updated==0 on empty batch, got %d", ts.Updated)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark: %v", err)
	}
	if wm != "2027-01-01T00:00:00Z" {
		t.Fatalf("expected watermark unchanged 2027-01-01T00:00:00Z on empty batch, got %q", wm)
	}
}