package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestWmR2B04MillisTruncatedToSecond(t *testing.T) {
	dir := t.TempDir()
	p := writeCSVStr(t, dir, "a.csv", "id,updated_at\n1,2026-10-20T10:00:00.123Z\n2,2026-10-20T10:00:00.456Z\n3,2026-10-20T10:00:00Z\n")

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	stats := runSync(t, st, src, "j1")
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 3 {
		t.Fatalf("Inserted = %d, want 3", ts.Inserted)
	}

	wm, _ := st.GetWatermark("s1", "t", "updated_at")
	// DATETIME canonical 形式为秒精度 RFC3339，毫秒在 ingestion 时截断（产品侧精度限制）。
	// 三行的毫秒部分 .123 / .456 均被丢弃，与整秒行归并到同一水位线。
	if wm != "2026-10-20T10:00:00Z" {
		t.Fatalf("watermark = %q, want %q", wm, "2026-10-20T10:00:00Z")
	}
}

func TestWmR2B04SameSecondMillisTreatedSimultaneous(t *testing.T) {
	dir := t.TempDir()
	p := writeCSVStr(t, dir, "a.csv", "id,updated_at\n1,2026-10-20T10:00:00.123Z\n2,2026-10-20T10:00:00.456Z\n3,2026-10-20T10:00:00Z\n")

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: p, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	stats := runSync(t, st, src, "j1")
	ts := tableStat(t, stats, "t")
	if ts.Inserted != 3 {
		t.Fatalf("Inserted = %d, want 3", ts.Inserted)
	}
	wm1, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm1 != "2026-10-20T10:00:00Z" {
		t.Fatalf("watermark = %q, want %q", wm1, "2026-10-20T10:00:00Z")
	}

	p2 := writeCSVStr(t, dir, "b.csv", "id,updated_at\n1,2026-10-20T10:00:00.123Z\n2,2026-10-20T10:00:00.456Z\n3,2026-10-20T10:00:00Z\n4,2026-10-20T10:00:00.789Z\n5,2026-10-20T10:00:01Z\n")
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}

	stats2 := runSync(t, st, src2, "j2")
	ts2 := tableStat(t, stats2, "t")
	// .789Z 截断到秒后等于当前水位线 "2026-10-20T10:00:00Z"，被增量过滤；
	// 只有整秒更大的 "2026-10-20T10:00:01Z" 行通过。
	if ts2.Inserted != 1 {
		t.Fatalf("Inserted = %d, want 1", ts2.Inserted)
	}
	wm2, _ := st.GetWatermark("s1", "t", "updated_at")
	if wm2 != "2026-10-20T10:00:01Z" {
		t.Fatalf("watermark = %q, want %q", wm2, "2026-10-20T10:00:01Z")
	}
}
