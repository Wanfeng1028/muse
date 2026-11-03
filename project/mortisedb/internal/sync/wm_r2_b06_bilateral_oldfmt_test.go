package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B06PresetNewFormatOldFormatRowFiltered(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	if err := st.SetWatermark("s1", "t", "updated_at", "2026-10-20T10:00:00Z"); err != nil {
		t.Fatalf("set watermark: %v", err)
	}

	dir := t.TempDir()
	p := writeCSVStr(t, dir, "t.csv", "id,updated_at\n1,2026-10-20 10:00:00\n2,2026-10-20 10:00:01\n")

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, src, "job1")

	ts := tableStat(t, stats, "t")
	if ts.Inserted != 1 {
		t.Fatalf("inserted = %d, want 1", ts.Inserted)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark: %v", err)
	}
	if wm != "2026-10-20T10:00:01Z" {
		t.Fatalf("watermark = %q, want %q", wm, "2026-10-20T10:00:01Z")
	}
}

func TestWmR2B06SlashFormatSameInstant(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	if err := st.SetWatermark("s1", "t", "updated_at", "2026-10-20T10:00:00Z"); err != nil {
		t.Fatalf("set watermark: %v", err)
	}

	dir := t.TempDir()
	p := writeCSVStr(t, dir, "t.csv", "id,updated_at\n1,2026/10/20 10:00:00\n2,2026/10/20 12:00:00\n")

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats := runSync(t, st, src, "job1")

	ts := tableStat(t, stats, "t")
	if ts.Inserted != 1 {
		t.Fatalf("inserted = %d, want 1", ts.Inserted)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark: %v", err)
	}
	if wm != "2026-10-20T12:00:00Z" {
		t.Fatalf("watermark = %q, want %q", wm, "2026-10-20T12:00:00Z")
	}
}
