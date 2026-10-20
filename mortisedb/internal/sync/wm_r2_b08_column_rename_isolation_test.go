package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B08ColumnRenameKeepsOldWatermark(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()

	csv1 := "id,updated_at\n1,2026-10-20 10:00:00\n2,2026-10-20 10:00:00\n"
	path1 := writeCSVStr(t, dir, "one.csv", csv1)

	src1 := config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        path1,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	stats1 := runSync(t, st, src1, "job-b08-1")
	ts1 := tableStat(t, stats1, "t")
	if ts1.Inserted != 2 {
		t.Fatalf("round1 inserted = %d, want 2", ts1.Inserted)
	}

	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark updated_at: %v", err)
	}
	if wm != "2026-10-20T10:00:00Z" {
		t.Fatalf("round1 updated_at watermark = %q, want %q", wm, "2026-10-20T10:00:00Z")
	}

	csv2 := "id,created_at\n1,2026-10-21 10:00:00\n2,2026-10-21 10:00:00\n"
	path2 := writeCSVStr(t, dir, "two.csv", csv2)

	src2 := config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        path2,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:created_at",
	}
	stats2 := runSync(t, st, src2, "job-b08-2")
	ts2 := tableStat(t, stats2, "t")
	// 同主键换增量列：行已存在且内容变化 -> 走同源更新分支，Updated==2（不是 Inserted）
	if ts2.Updated != 2 {
		t.Fatalf("round2 updated = %d, want 2", ts2.Updated)
	}

	wmCreated, err := st.GetWatermark("s1", "t", "created_at")
	if err != nil {
		t.Fatalf("get watermark created_at: %v", err)
	}
	if wmCreated != "2026-10-21T10:00:00Z" {
		t.Fatalf("round2 created_at watermark = %q, want %q", wmCreated, "2026-10-21T10:00:00Z")
	}

	wmUpdated, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark updated_at after rename: %v", err)
	}
	if wmUpdated != "2026-10-20T10:00:00Z" {
		t.Fatalf("updated_at watermark after rename = %q, want %q (old column must be preserved)", wmUpdated, "2026-10-20T10:00:00Z")
	}
}

func TestWmR2B08TwoIncrementalColumnsIndependentRounds(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	dir := t.TempDir()

	csv1 := "id,updated_at\n1,2026-10-20 10:00:00\n2,2026-10-20 10:00:00\n"
	path1 := writeCSVStr(t, dir, "one.csv", csv1)
	src1 := config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        path1,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	stats1 := runSync(t, st, src1, "job-b08-r1")
	if ts := tableStat(t, stats1, "t"); ts.Inserted != 2 {
		t.Fatalf("round1 inserted = %d, want 2", ts.Inserted)
	}

	csv2 := "id,created_at\n1,2026-10-21 10:00:00\n2,2026-10-21 10:00:00\n"
	path2 := writeCSVStr(t, dir, "two.csv", csv2)
	src2 := config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        path2,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:created_at",
	}
	stats2 := runSync(t, st, src2, "job-b08-r2")
	if ts := tableStat(t, stats2, "t"); ts.Updated != 2 {
		t.Fatalf("round2 updated = %d, want 2", ts.Updated)
	}

	wmCreated, err := st.GetWatermark("s1", "t", "created_at")
	if err != nil {
		t.Fatalf("get watermark created_at before round3: %v", err)
	}
	if wmCreated != "2026-10-21T10:00:00Z" {
		t.Fatalf("created_at watermark before round3 = %q, want %q", wmCreated, "2026-10-21T10:00:00Z")
	}

	wmUpdatedBefore, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark updated_at before round3: %v", err)
	}
	if wmUpdatedBefore != "2026-10-20T10:00:00Z" {
		t.Fatalf("updated_at watermark before round3 = %q, want %q", wmUpdatedBefore, "2026-10-20T10:00:00Z")
	}

	csv3 := "id,created_at\n1,2026-10-21 10:00:00\n2,2026-10-21 10:00:00\n3,2026-10-22 10:00:00\n"
	path3 := writeCSVStr(t, dir, "three.csv", csv3)
	src3 := config.SourceConfig{
		Type:        "csv",
		Name:        "s1",
		Path:        path3,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:created_at",
	}
	stats3 := runSync(t, st, src3, "job-b08-r3")
	ts3 := tableStat(t, stats3, "t")
	if ts3.Inserted != 1 {
		t.Fatalf("round3 inserted = %d, want 1", ts3.Inserted)
	}

	wmCreatedAfter, err := st.GetWatermark("s1", "t", "created_at")
	if err != nil {
		t.Fatalf("get watermark created_at after round3: %v", err)
	}
	if wmCreatedAfter != "2026-10-22T10:00:00Z" {
		t.Fatalf("created_at watermark after round3 = %q, want %q", wmCreatedAfter, "2026-10-22T10:00:00Z")
	}

	wmUpdatedAfter, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("get watermark updated_at after round3: %v", err)
	}
	if wmUpdatedAfter != "2026-10-20T10:00:00Z" {
		t.Fatalf("updated_at watermark after round3 = %q, want %q (must not advance)", wmUpdatedAfter, "2026-10-20T10:00:00Z")
	}
}
