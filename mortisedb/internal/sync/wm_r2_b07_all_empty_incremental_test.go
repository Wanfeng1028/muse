package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B07AllEmptyNoWatermarkWritten(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()
	p := writeCSVStr(t, dir, "t.csv", "id,updated_at\n1,\n2,\n3,\n")

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	stats := runSync(t, st, src, "job1")
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 3 {
		t.Fatalf("Inserted = %d, want 3", ts.Inserted)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark: %v", err)
	}
	if wm != "" {
		t.Fatalf("watermark = %q, want empty", wm)
	}
}

func TestWmR2B07SecondRoundFullResyncAllSkipped(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()
	p := writeCSVStr(t, dir, "t.csv", "id,updated_at\n1,\n2,\n3,\n")

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	first := runSync(t, st, src, "job1")
	fts := tableStat(t, first, "t")
	if fts.Inserted != 3 {
		t.Fatalf("first Inserted = %d, want 3", fts.Inserted)
	}
	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark after first: %v", err)
	}
	if wm != "" {
		t.Fatalf("watermark after first = %q, want empty", wm)
	}

	second := runSync(t, st, src, "job1")
	sts := tableStat(t, second, "t")
	if sts.Inserted != 0 {
		t.Fatalf("second Inserted = %d, want 0", sts.Inserted)
	}
	if sts.Skipped != 3 {
		t.Fatalf("second Skipped = %d, want 3", sts.Skipped)
	}

	wm2, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark after second: %v", err)
	}
	if wm2 != "" {
		t.Fatalf("watermark after second = %q, want empty", wm2)
	}
}
