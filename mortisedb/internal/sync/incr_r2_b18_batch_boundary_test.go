package sync

import (
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func buildBatchCSV(n int) (string, string) {
	base := time.Date(2026, 10, 20, 10, 0, 0, 0, time.UTC)
	var b strings.Builder
	b.WriteString("id,updated_at\n")
	for i := 1; i <= n; i++ {
		ts := base.Add(time.Duration(i-1) * time.Second)
		fmt.Fprintf(&b, "%d,%s\n", i, ts.Format("2006-01-02 15:04:05"))
	}
	last := base.Add(time.Duration(n-1) * time.Second).Format(time.RFC3339)
	return b.String(), last
}

func findTableStat(stats []SourceStats, name string) (TableStats, bool) {
	for _, s := range stats {
		for _, tb := range s.Tables {
			if tb.Table == name {
				return tb, true
			}
		}
	}
	return TableStats{}, false
}

func TestIncrR2B18ExactlyBatchSize(t *testing.T) {
	const n = 5000

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	csvContent, wantWatermark := buildBatchCSV(n)
	dir := t.TempDir()
	csvPath := writeCSVStr(t, dir, "t.csv", csvContent)

	src := config.SourceConfig{
		Name:        "s1",
		Type:        "csv",
		Path:        csvPath,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 5000},
	}

	stats, err := Sync(cfg, st, []string{src.Name}, "j1")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	ts, ok := findTableStat(stats, "t")
	if !ok {
		t.Fatalf("未找到表 t 的统计项, stats=%+v", stats)
	}
	if ts.Inserted != 5000 {
		t.Fatalf("Inserted 期望 5000, 实际 %d", ts.Inserted)
	}

	cnt, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if cnt != 5000 {
		t.Fatalf("TableCount 期望 5000, 实际 %d", cnt)
	}

	wm, err := st.GetWatermark(src.Name, "t", "updated_at")
	if err != nil {
		t.Fatalf("GetWatermark 失败: %v", err)
	}
	if wm != wantWatermark {
		t.Fatalf("水位线期望 %q, 实际 %q", wantWatermark, wm)
	}
}

func TestIncrR2B18CrossesBoundary(t *testing.T) {
	const n = 5001

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	csvContent, wantWatermark := buildBatchCSV(n)
	dir := t.TempDir()
	csvPath := writeCSVStr(t, dir, "t.csv", csvContent)

	src := config.SourceConfig{
		Name:        "s1",
		Type:        "csv",
		Path:        csvPath,
		Table:       "t",
		PrimaryKey:  "id",
		Incremental: "column:updated_at",
	}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", BatchSize: 5000},
	}

	// 提交次数语义: 5001 行中, processed%batchSize==0 仅在第 5000 行触发一次 commitBatch;
	// 剩余 1 行在第 5001 行处不触发, 由循环结束后的最终提交落库。
	// 因此总计两次提交: 第 5000 行批量提交 + 尾部最终提交。
	stats, err := Sync(cfg, st, []string{src.Name}, "j1")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	ts, ok := findTableStat(stats, "t")
	if !ok {
		t.Fatalf("未找到表 t 的统计项, stats=%+v", stats)
	}
	if ts.Inserted != 5001 {
		t.Fatalf("Inserted 期望 5001, 实际 %d", ts.Inserted)
	}

	cnt, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("TableCount 失败: %v", err)
	}
	if cnt != 5001 {
		t.Fatalf("TableCount 期望 5001, 实际 %d", cnt)
	}

	wm, err := st.GetWatermark(src.Name, "t", "updated_at")
	if err != nil {
		t.Fatalf("GetWatermark 失败: %v", err)
	}
	if wm != wantWatermark {
		t.Fatalf("水位线期望 %q, 实际 %q", wantWatermark, wm)
	}
}
