package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B03SameInstantDifferentTZ(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n" +
		"1,2026-10-20T10:00:00+08:00\n" +
		"2,2026-10-20T02:00:00Z\n"
	path := writeCSVStr(t, dir, "same_instant.csv", csv)

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	src := config.SourceConfig{
		Type:         "csv",
		Name:         "s1",
		Path:         path,
		Table:        "t",
		PrimaryKey:   "id",
		Incremental:  "column:updated_at",
	}

	stats := runSync(t, st, src, "job1")
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 2 {
		t.Fatalf("first sync inserted = %d, want 2", ts.Inserted)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark: %v", err)
	}
	if wm != "2026-10-20T02:00:00Z" {
		t.Fatalf("watermark = %q, want %q", wm, "2026-10-20T02:00:00Z")
	}

	stats2 := runSync(t, st, src, "job1")
	ts2 := tableStat(t, stats2, "t")
	if ts2.Inserted != 0 {
		t.Fatalf("second sync inserted = %d, want 0", ts2.Inserted)
	}
}

func TestWmR2B03PositiveNegativeOffset(t *testing.T) {
	dir := t.TempDir()
	csv := "id,updated_at\n" +
		"1,2026-10-20T10:00:00+08:00\n" +
		"2,2026-10-19T22:00:00-05:00\n"
	path := writeCSVStr(t, dir, "offset.csv", csv)

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	src := config.SourceConfig{
		Type:         "csv",
		Name:         "s1",
		Path:         path,
		Table:        "t",
		PrimaryKey:   "id",
		Incremental:  "column:updated_at",
	}

	stats := runSync(t, st, src, "job1")
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 2 {
		t.Fatalf("first sync inserted = %d, want 2", ts.Inserted)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark: %v", err)
	}
	if wm != "2026-10-20T03:00:00Z" {
		t.Fatalf("watermark = %q, want %q", wm, "2026-10-20T03:00:00Z")
	}
}
