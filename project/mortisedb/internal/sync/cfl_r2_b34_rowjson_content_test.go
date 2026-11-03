package sync

import (
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestCflR2B34RowJSONContent(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	dir := t.TempDir()
	pathA := writeCSVStr(t, dir, "a.csv", "id,name\n1,a1\n")
	pathB := writeCSVStr(t, dir, "b.csv", "id,name\n1,b1\n")

	tableStatOf := func(stats []SourceStats, source, table string) *TableStats {
		for i := range stats {
			if stats[i].Source != source {
				continue
			}
			for j := range stats[i].Tables {
				if stats[i].Tables[j].Table == table {
					return &stats[i].Tables[j]
				}
			}
		}
		return nil
	}

	srcA := config.SourceConfig{Type: "csv", Name: "A", Path: pathA, Table: "t", PrimaryKey: "id", Incremental: ""}
	srcB := config.SourceConfig{Type: "csv", Name: "B", Path: pathB, Table: "t", PrimaryKey: "id", Incremental: ""}
	cfg := &config.Config{
		Sources: []config.SourceConfig{srcA, srcB},
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"A", "B"}, BatchSize: 100},
	}

	stats1, err := Sync(cfg, st, []string{"A"}, "job1")
	if err != nil {
		t.Fatalf("round1 Sync 失败: %v", err)
	}
	if len(stats1) != 1 {
		t.Fatalf("round1 stats 长度 = %d, want 1", len(stats1))
	}
	ts1 := tableStatOf(stats1, "A", "t")
	if ts1 == nil || ts1.Inserted != 1 {
		t.Fatalf("round1 Inserted 期望 1，实际 %+v", ts1)
	}

	stats2, err := Sync(cfg, st, []string{"B"}, "job2")
	if err != nil {
		t.Fatalf("round2 Sync 失败: %v", err)
	}
	if len(stats2) != 1 {
		t.Fatalf("round2 stats 长度 = %d, want 1", len(stats2))
	}
	ts2 := tableStatOf(stats2, "B", "t")
	if ts2 == nil || ts2.Conflicts != 1 {
		t.Fatalf("round2 Conflicts 期望 1，实际 %+v", ts2)
	}

	pend, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts 失败: %v", err)
	}
	if len(pend) != 1 {
		t.Fatalf("pending 冲突数 = %d, want 1", len(pend))
	}
	c := pend[0]
	if c.TableName != "t" {
		t.Fatalf("TableName = %q, want %q", c.TableName, "t")
	}
	if c.PK != "1" {
		t.Fatalf("PK = %q, want %q", c.PK, "1")
	}
	if c.SourceA != "A" {
		t.Fatalf("SourceA = %q, want %q", c.SourceA, "A")
	}
	if c.SourceB != "B" {
		t.Fatalf("SourceB = %q, want %q", c.SourceB, "B")
	}
	// Go map 序列化键顺序随机，只做子串断言。
	if !strings.Contains(c.RowJSON, `"name":"b1"`) {
		t.Fatalf("RowJSON 缺少挑战方 B 的列值 name=b1, got %q", c.RowJSON)
	}
	if !strings.Contains(c.RowJSON, `"id":1`) {
		t.Fatalf("RowJSON 缺少主键 id=1, got %q", c.RowJSON)
	}
}
