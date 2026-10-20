package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B11EmptyValuePassesFilter(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()

	round1 := "id,updated_at\n1,2026-10-20 10:00:00\n"
	p1 := writeCSVStr(t, dir, "round1.csv", round1)
	src1 := config.SourceConfig{Type: "csv", Name: "s1", Path: p1, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats1 := runSync(t, st, src1, "job1")
	s1 := tableStat(t, stats1, "t")
	if s1.Inserted != 1 {
		t.Fatalf("round1 inserted = %d, want 1", s1.Inserted)
	}

	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark round1: %v", err)
	}
	if wm1 != "2026-10-20T10:00:00Z" {
		t.Fatalf("round1 watermark = %q, want %q", wm1, "2026-10-20T10:00:00Z")
	}

	round2 := "id,updated_at\n2,\n3,2026-10-20 09:00:00\n4,2026-10-20 11:00:00\n"
	p2 := writeCSVStr(t, dir, "round2.csv", round2)
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats2 := runSync(t, st, src2, "job2")
	s2 := tableStat(t, stats2, "t")
	if s2.Inserted != 2 {
		t.Fatalf("round2 inserted = %d, want 2", s2.Inserted)
	}
	if s2.Skipped != 0 {
		t.Fatalf("round2 skipped = %d, want 0", s2.Skipped)
	}

	wm2, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark round2: %v", err)
	}
	if wm2 != "2026-10-20T11:00:00Z" {
		t.Fatalf("round2 watermark = %q, want %q", wm2, "2026-10-20T11:00:00Z")
	}
}

func TestWmR2B11EmptyValueRowNotSkippedTwice(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()

	round1 := "id,updated_at\n1,2026-10-20 10:00:00\n"
	p1 := writeCSVStr(t, dir, "round1.csv", round1)
	src1 := config.SourceConfig{Type: "csv", Name: "s1", Path: p1, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats1 := runSync(t, st, src1, "job1")
	s1 := tableStat(t, stats1, "t")
	if s1.Inserted != 1 {
		t.Fatalf("round1 inserted = %d, want 1", s1.Inserted)
	}

	round2 := "id,updated_at\n2,\n3,2026-10-20 09:00:00\n4,2026-10-20 11:00:00\n"
	p2 := writeCSVStr(t, dir, "round2.csv", round2)
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats2 := runSync(t, st, src2, "job2")
	s2 := tableStat(t, stats2, "t")
	if s2.Inserted != 2 {
		t.Fatalf("round2 inserted = %d, want 2", s2.Inserted)
	}

	round3 := "id,updated_at\n2,\n"
	p3 := writeCSVStr(t, dir, "round3.csv", round3)
	src3 := config.SourceConfig{Type: "csv", Name: "s1", Path: p3, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats3 := runSync(t, st, src3, "job3")
	s3 := tableStat(t, stats3, "t")
	if s3.Inserted != 0 {
		t.Fatalf("round3 inserted = %d, want 0", s3.Inserted)
	}
	if s3.Skipped != 1 {
		t.Fatalf("round3 skipped = %d, want 1", s3.Skipped)
	}

	wm3, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark round3: %v", err)
	}
	if wm3 != "2026-10-20T11:00:00Z" {
		t.Fatalf("round3 watermark = %q, want %q", wm3, "2026-10-20T11:00:00Z")
	}
}
