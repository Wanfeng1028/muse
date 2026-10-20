package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestIncrR2B15EqualWatermarkNotRepulled(t *testing.T) {
	dir := t.TempDir()
	p1 := writeCSVStr(t, dir, "r1.csv", "id,updated_at\n1,2026-10-20 10:00:00\n2,2026-10-20 11:00:00\n")

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src1 := config.SourceConfig{Type: "csv", Name: "s1", Path: p1, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats1 := runSync(t, st, src1, "j1")
	ts1 := tableStat(t, stats1, "t")
	if ts1.Inserted != 2 {
		t.Fatalf("第一轮 Inserted = %d, want 2", ts1.Inserted)
	}

	wm1, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("GetWatermark 失败: %v", err)
	}
	if wm1 != "2026-10-20T11:00:00Z" {
		t.Fatalf("第一轮水位线 = %q, want %q", wm1, "2026-10-20T11:00:00Z")
	}

	p2 := writeCSVStr(t, dir, "r2.csv", "id,updated_at\n3,2026-10-20T11:00:00Z\n4,2026-10-20 11:00:00\n5,2026-10-20 12:00:00\n")
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats2 := runSync(t, st, src2, "j2")
	ts2 := tableStat(t, stats2, "t")
	if ts2.Inserted != 1 {
		t.Fatalf("第二轮 Inserted = %d, want 1", ts2.Inserted)
	}

	wm2, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("GetWatermark 失败: %v", err)
	}
	if wm2 != "2026-10-20T12:00:00Z" {
		t.Fatalf("第二轮水位线 = %q, want %q", wm2, "2026-10-20T12:00:00Z")
	}
}

func TestIncrR2B15AllEqualNothingInserted(t *testing.T) {
	dir := t.TempDir()
	p1 := writeCSVStr(t, dir, "r1.csv", "id,updated_at\n1,2026-10-20 10:00:00\n2,2026-10-20 11:00:00\n")

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	src1 := config.SourceConfig{Type: "csv", Name: "s1", Path: p1, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src1, "j1")

	p2 := writeCSVStr(t, dir, "r2.csv", "id,updated_at\n3,2026-10-20T11:00:00Z\n4,2026-10-20 11:00:00\n5,2026-10-20 12:00:00\n")
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: p2, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	runSync(t, st, src2, "j2")

	wm2, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("GetWatermark 失败: %v", err)
	}
	if wm2 != "2026-10-20T12:00:00Z" {
		t.Fatalf("前置水位线 = %q, want %q", wm2, "2026-10-20T12:00:00Z")
	}

	p3 := writeCSVStr(t, dir, "r3.csv", "id,updated_at\n6,2026-10-20T12:00:00Z\n7,2026-10-20T12:00:00Z\n8,2026-10-20T12:00:00Z\n")
	src3 := config.SourceConfig{Type: "csv", Name: "s1", Path: p3, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	stats3 := runSync(t, st, src3, "j3")
	ts3 := tableStat(t, stats3, "t")
	if ts3.Inserted != 0 {
		t.Fatalf("第三轮 Inserted = %d, want 0", ts3.Inserted)
	}

	cnt, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if cnt != 3 {
		t.Fatalf("TableCount = %d, want 3", cnt)
	}
}
