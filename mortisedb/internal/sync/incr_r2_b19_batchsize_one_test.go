package sync

import (
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func buildB19CSV(startID, count int, base time.Time) string {
	var b strings.Builder
	b.WriteString("id,name,updated_at\n")
	for i := 0; i < count; i++ {
		id := startID + i
		ts := base.Add(time.Duration(i) * time.Minute).Format("2006-01-02 15:04:05")
		fmt.Fprintf(&b, "%d,name-%d,%s\n", id, id, ts)
	}
	return b.String()
}

func findB19Table(stats []SourceStats, table string) *TableStats {
	for i := range stats {
		for j := range stats[i].Tables {
			if stats[i].Tables[j].Table == table {
				return &stats[i].Tables[j]
			}
		}
	}
	return nil
}

func TestIncrR2B19BatchSizeOneCorrectness(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	base := time.Date(2026, 10, 20, 10, 0, 0, 0, time.UTC)
	dir := t.TempDir()
	csvPath := writeCSVStr(t, dir, "t.csv", buildB19CSV(1, 50, base))

	src := config.SourceConfig{Type: "csv", Name: "s1", Path: csvPath, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 1},
	}
	stats, err := Sync(cfg, st, []string{src.Name}, "j1")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	ts := findB19Table(stats, "t")
	if ts == nil {
		t.Fatalf("stats 中未找到表 t")
	}
	if ts.Inserted != 50 {
		t.Fatalf("Inserted = %d, 期望 50", ts.Inserted)
	}
	if ts.Updated != 0 {
		t.Fatalf("Updated = %d, 期望 0", ts.Updated)
	}
	if ts.Deleted != 0 {
		t.Fatalf("Deleted = %d, 期望 0", ts.Deleted)
	}

	cnt, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if cnt != 50 {
		t.Fatalf("TableCount(t) = %d, 期望 50", cnt)
	}

	want := base.Add(49 * time.Minute).Format(time.RFC3339)
	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("GetWatermark 失败: %v", err)
	}
	if wm != want {
		t.Fatalf("水位线 = %q, 期望 %q", wm, want)
	}
}

func TestIncrR2B19BatchSizeOneSecondRound(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	base := time.Date(2026, 10, 20, 10, 0, 0, 0, time.UTC)
	dir := t.TempDir()

	csvPath := writeCSVStr(t, dir, "t.csv", buildB19CSV(1, 50, base))
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: csvPath, Table: "t", PrimaryKey: "id", Incremental: "column:updated_at"}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 1},
	}

	if _, err := Sync(cfg, st, []string{src.Name}, "j1"); err != nil {
		t.Fatalf("第一轮 Sync 失败: %v", err)
	}

	cnt, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if cnt != 50 {
		t.Fatalf("第一轮后 TableCount(t) = %d, 期望 50", cnt)
	}

	writeCSVStr(t, dir, "t.csv", buildB19CSV(1, 60, base))
	stats, err := Sync(cfg, st, []string{src.Name}, "j1")
	if err != nil {
		t.Fatalf("第二轮 Sync 失败: %v", err)
	}

	ts := findB19Table(stats, "t")
	if ts == nil {
		t.Fatalf("stats 中未找到表 t")
	}
	if ts.Inserted != 10 {
		t.Fatalf("第二轮 Inserted = %d, 期望 10", ts.Inserted)
	}
	// 旧 50 行 updated_at 不大于水位线，被连接器过滤，不计入 Skipped
	if ts.Skipped != 0 {
		t.Fatalf("第二轮 Skipped = %d, 期望 0（旧行被过滤，不计入跳过）", ts.Skipped)
	}
	if ts.Updated != 0 {
		t.Fatalf("第二轮 Updated = %d, 期望 0", ts.Updated)
	}

	cnt, err = st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if cnt != 60 {
		t.Fatalf("第二轮后 TableCount(t) = %d, 期望 60", cnt)
	}

	want := base.Add(59 * time.Minute).Format(time.RFC3339)
	wm, err := st.GetWatermark("s1", "t", "updated_at")
	if err != nil {
		t.Fatalf("GetWatermark 失败: %v", err)
	}
	if wm != want {
		t.Fatalf("第二轮水位线 = %q, 期望 %q", wm, want)
	}
}
