package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestCflR2B36UnknownPriorityPends(t *testing.T) {
	if got := PriorityIndex([]string{"X", "Y"}, "A"); got != 1<<30 {
		t.Fatalf("PriorityIndex A = %d, 期望 %d", got, 1<<30)
	}
	if got := PriorityIndex([]string{"X", "Y"}, "B"); got != 1<<30 {
		t.Fatalf("PriorityIndex B = %d, 期望 %d", got, 1<<30)
	}

	dir := t.TempDir()
	pathA := writeCSVStr(t, dir, "a.csv", "id,name\n1,a1\n")
	pathB := writeCSVStr(t, dir, "b.csv", "id,name\n1,b1\n")

	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	srcA := config.SourceConfig{Type: "csv", Name: "A", Path: pathA, Table: "t", PrimaryKey: "id", Incremental: ""}
	srcB := config.SourceConfig{Type: "csv", Name: "B", Path: pathB, Table: "t", PrimaryKey: "id", Incremental: ""}

	cfg := &config.Config{
		Sources: []config.SourceConfig{srcA, srcB},
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"X", "Y"}, BatchSize: 100},
	}

	stats, err := Sync(cfg, st, []string{"A"}, "j1")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	var tsA *TableStats
	for i := range stats {
		if stats[i].Source != "A" {
			continue
		}
		for j := range stats[i].Tables {
			if stats[i].Tables[j].Table == "t" {
				tsA = &stats[i].Tables[j]
			}
		}
	}
	if tsA == nil {
		t.Fatalf("未找到源 A 表 t 的统计")
	}
	if tsA.Inserted != 1 {
		t.Fatalf("源 A 表 t Inserted = %d, 期望 1", tsA.Inserted)
	}

	stats2, err := Sync(cfg, st, []string{"B"}, "j2")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	var ts *TableStats
	for i := range stats2 {
		if stats2[i].Source != "B" {
			continue
		}
		for j := range stats2[i].Tables {
			if stats2[i].Tables[j].Table == "t" {
				ts = &stats2[i].Tables[j]
			}
		}
	}
	if ts == nil {
		t.Fatalf("未找到源 B 表 t 的统计")
	}
	if ts.Conflicts != 1 {
		t.Fatalf("源 B 表 t Conflicts = %d, 期望 1", ts.Conflicts)
	}
	if ts.Updated != 0 {
		t.Fatalf("源 B 表 t Updated = %d, 期望 0", ts.Updated)
	}

	var name string
	if err := st.DB.QueryRow("SELECT \"name\" FROM \"t\" WHERE \"id\"='1'").Scan(&name); err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if name != "a1" {
		t.Fatalf("name = %q, 期望 %q", name, "a1")
	}

	pend, _ := st.ListConflicts("pending")
	if len(pend) != 1 {
		t.Fatalf("pending 冲突数 = %d, 期望 1", len(pend))
	}
	if pend[0].SourceA != "A" {
		t.Fatalf("SourceA = %q, 期望 %q", pend[0].SourceA, "A")
	}
	if pend[0].SourceB != "B" {
		t.Fatalf("SourceB = %q, 期望 %q", pend[0].SourceB, "B")
	}
}
