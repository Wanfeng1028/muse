package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B09MonotonicAcrossThreeRounds(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()
	p := writeCSVStr(t, dir, "data.csv", "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20 10:00:00\n")

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	stats1 := runSync(t, st, src, "job1")
	ts1 := tableStat(t, stats1, "t")
	if ts1.Inserted != 2 {
		t.Fatalf("round1 inserted = %d, want 2", ts1.Inserted)
	}

	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("round1 get watermark: %v", err)
	}
	if wm1 != "2026-10-20T10:00:00Z" {
		t.Fatalf("round1 watermark = %q, want %q", wm1, "2026-10-20T10:00:00Z")
	}

	p = writeCSVStr(t, dir, "data.csv", "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20 10:00:00\n3,2026-10-20 11:00:00\n")

	stats2 := runSync(t, st, src, "job2")
	ts2 := tableStat(t, stats2, "t")
	if ts2.Inserted != 1 {
		t.Fatalf("round2 inserted = %d, want 1", ts2.Inserted)
	}

	wm2, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("round2 get watermark: %v", err)
	}
	if wm2 != "2026-10-20T11:00:00Z" {
		t.Fatalf("round2 watermark = %q, want %q", wm2, "2026-10-20T11:00:00Z")
	}

	p = writeCSVStr(t, dir, "data.csv", "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20 10:00:00\n3,2026-10-20 11:00:00\n4,2026-10-20 09:30:00\n")

	stats3 := runSync(t, st, src, "job3")
	ts3 := tableStat(t, stats3, "t")
	if ts3.Inserted != 0 {
		t.Fatalf("round3 inserted = %d, want 0", ts3.Inserted)
	}

	wm3, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("round3 get watermark: %v", err)
	}
	if wm3 != "2026-10-20T11:00:00Z" {
		t.Fatalf("round3 watermark = %q, want %q", wm3, "2026-10-20T11:00:00Z")
	}
}

func TestWmR2B09LateDataNotInsertedNorCounted(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()
	p := writeCSVStr(t, dir, "data.csv", "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20 10:00:00\n")

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	runSync(t, st, src, "job1")

	p = writeCSVStr(t, dir, "data.csv", "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20 10:00:00\n3,2026-10-20 11:00:00\n")
	runSync(t, st, src, "job2")

	p = writeCSVStr(t, dir, "data.csv", "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20 10:00:00\n3,2026-10-20 11:00:00\n4,2026-10-20 09:30:00\n")
	stats3 := runSync(t, st, src, "job3")
	ts3 := tableStat(t, stats3, "t")
	if ts3.Inserted != 0 {
		t.Fatalf("round3 inserted = %d, want 0", ts3.Inserted)
	}

	cnt3, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("round3 table count: %v", err)
	}
	if cnt3 != 3 {
		t.Fatalf("round3 table count = %d, want 3", cnt3)
	}

	wm3, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("round3 get watermark: %v", err)
	}
	if wm3 != "2026-10-20T11:00:00Z" {
		t.Fatalf("round3 watermark = %q, want %q", wm3, "2026-10-20T11:00:00Z")
	}

	p = writeCSVStr(t, dir, "data.csv", "id,updated_at\n1,2026-10-20 09:00:00\n2,2026-10-20 10:00:00\n3,2026-10-20 11:00:00\n4,2026-10-20 09:30:00\n5,2026-10-20 12:00:00\n")
	stats4 := runSync(t, st, src, "job4")
	ts4 := tableStat(t, stats4, "t")
	if ts4.Inserted != 1 {
		t.Fatalf("round4 inserted = %d, want 1", ts4.Inserted)
	}

	cnt4, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("round4 table count: %v", err)
	}
	if cnt4 != 4 {
		t.Fatalf("round4 table count = %d, want 4", cnt4)
	}

	wm4, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("round4 get watermark: %v", err)
	}
	if wm4 != "2026-10-20T12:00:00Z" {
		t.Fatalf("round4 watermark = %q, want %q", wm4, "2026-10-20T12:00:00Z")
	}
}
