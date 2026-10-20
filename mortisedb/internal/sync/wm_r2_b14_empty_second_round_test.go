package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B14EmptySecondRoundKeepsWatermark(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()

	round1 := "id,updated_at\n1,2026-10-20 10:00:00\n2,2026-10-20 10:00:00\n"
	p1 := writeCSVStr(t, dir, "round1.csv", round1)
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p1, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	stats1 := runSync(t, st, src, "job1")
	ts1 := tableStat(t, stats1, "t")
	if ts1.Inserted != 2 {
		t.Fatalf("round1 inserted = %d, want 2", ts1.Inserted)
	}

	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark round1: %v", err)
	}
	if wm1 != "2026-10-20T10:00:00Z" {
		t.Fatalf("round1 watermark = %q, want %q", wm1, "2026-10-20T10:00:00Z")
	}

	round2 := "id,updated_at\n"
	p2 := writeCSVStr(t, dir, "round2.csv", round2)
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	stats2 := runSync(t, st, src2, "job2")
	ts2 := tableStat(t, stats2, "t")
	if ts2.Inserted != 0 {
		t.Fatalf("round2 inserted = %d, want 0", ts2.Inserted)
	}
	if ts2.Updated != 0 {
		t.Fatalf("round2 updated = %d, want 0", ts2.Updated)
	}
	if ts2.Deleted != 0 {
		t.Fatalf("round2 deleted = %d, want 0", ts2.Deleted)
	}

	wm2, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark round2: %v", err)
	}
	if wm2 != "2026-10-20T10:00:00Z" {
		t.Fatalf("round2 watermark = %q, want %q", wm2, "2026-10-20T10:00:00Z")
	}
}

func TestWmR2B14ThirdRoundResumes(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()

	round1 := "id,updated_at\n1,2026-10-20 10:00:00\n2,2026-10-20 10:00:00\n"
	p1 := writeCSVStr(t, dir, "round1.csv", round1)
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p1, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	stats1 := runSync(t, st, src, "job1")
	ts1 := tableStat(t, stats1, "t")
	if ts1.Inserted != 2 {
		t.Fatalf("round1 inserted = %d, want 2", ts1.Inserted)
	}

	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark round1: %v", err)
	}
	if wm1 != "2026-10-20T10:00:00Z" {
		t.Fatalf("round1 watermark = %q, want %q", wm1, "2026-10-20T10:00:00Z")
	}

	round2 := "id,updated_at\n"
	p2 := writeCSVStr(t, dir, "round2.csv", round2)
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	stats2 := runSync(t, st, src2, "job2")
	ts2 := tableStat(t, stats2, "t")
	if ts2.Inserted != 0 {
		t.Fatalf("round2 inserted = %d, want 0", ts2.Inserted)
	}
	if ts2.Updated != 0 {
		t.Fatalf("round2 updated = %d, want 0", ts2.Updated)
	}
	if ts2.Deleted != 0 {
		t.Fatalf("round2 deleted = %d, want 0", ts2.Deleted)
	}

	wm2, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark round2: %v", err)
	}
	if wm2 != "2026-10-20T10:00:00Z" {
		t.Fatalf("round2 watermark = %q, want %q", wm2, "2026-10-20T10:00:00Z")
	}

	round3 := "id,updated_at\n3,2026-10-20 11:00:00\n"
	p3 := writeCSVStr(t, dir, "round3.csv", round3)
	src3 := config.SourceConfig{Type: "csv", Name: "s1", Path: p3, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	stats3 := runSync(t, st, src3, "job3")
	ts3 := tableStat(t, stats3, "t")
	if ts3.Inserted != 1 {
		t.Fatalf("round3 inserted = %d, want 1", ts3.Inserted)
	}

	wm3, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark round3: %v", err)
	}
	if wm3 != "2026-10-20T11:00:00Z" {
		t.Fatalf("round3 watermark = %q, want %q", wm3, "2026-10-20T11:00:00Z")
	}
}
