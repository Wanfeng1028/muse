package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestCflR2B31SameContentKeepsPending(t *testing.T) {
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
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"A", "B"}, BatchSize: 100},
	}

	// round1: 源 A 首次写入，插入 1 行
	stats, err := Sync(cfg, st, []string{"A"}, "j1")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	var ts *TableStats
	for i := range stats {
		if stats[i].Source != "A" {
			continue
		}
		for j := range stats[i].Tables {
			if stats[i].Tables[j].Table == "t" {
				ts = &stats[i].Tables[j]
			}
		}
	}
	if ts == nil {
		t.Fatalf("未找到源 A 表 t 的统计")
	}
	if ts.Inserted != 1 {
		t.Fatalf("round1 期望 Inserted==1，实际 %d", ts.Inserted)
	}

	// round2: 源 B 写入不同内容，触发主键冲突，应记为 Conflicts==1 且 Updated==0
	stats2, err := Sync(cfg, st, []string{"B"}, "j2")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	var ts2 *TableStats
	for i := range stats2 {
		if stats2[i].Source != "B" {
			continue
		}
		for j := range stats2[i].Tables {
			if stats2[i].Tables[j].Table == "t" {
				ts2 = &stats2[i].Tables[j]
			}
		}
	}
	if ts2 == nil {
		t.Fatalf("未找到源 B 表 t 的统计")
	}
	if ts2.Conflicts != 1 {
		t.Fatalf("round2 期望 Conflicts==1，实际 %d", ts2.Conflicts)
	}
	if ts2.Updated != 0 {
		t.Fatalf("round2 期望 Updated==0，实际 %d", ts2.Updated)
	}
	pend, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts 失败: %v", err)
	}
	if len(pend) != 1 {
		t.Fatalf("round2 期望 pending 冲突数==1，实际 %d", len(pend))
	}

	// round3: 源 A 用完全相同的内容再写一轮。哈希相同走跳过分支，
	// 不会触发 ResolveConflictsByPK，因此 pending 冲突必须保留。
	// 只有内容真正变化的同源重写才会调用 ResolveConflictsByPK 自动解决 pending 冲突。
	stats3, err := Sync(cfg, st, []string{"A"}, "j3")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	var ts3 *TableStats
	for i := range stats3 {
		if stats3[i].Source != "A" {
			continue
		}
		for j := range stats3[i].Tables {
			if stats3[i].Tables[j].Table == "t" {
				ts3 = &stats3[i].Tables[j]
			}
		}
	}
	if ts3 == nil {
		t.Fatalf("未找到源 A 表 t 的统计")
	}
	if ts3.Skipped != 1 {
		t.Fatalf("round3 期望 Skipped==1，实际 %d", ts3.Skipped)
	}
	if ts3.Updated != 0 {
		t.Fatalf("round3 期望 Updated==0，实际 %d", ts3.Updated)
	}
	if ts3.Conflicts != 0 {
		t.Fatalf("round3 期望 Conflicts==0，实际 %d", ts3.Conflicts)
	}
	pend3, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts 失败: %v", err)
	}
	if len(pend3) != 1 {
		t.Fatalf("round3 期望 pending 冲突数==1（同内容重写不触发自动解决），实际 %d", len(pend3))
	}

	var name string
	if err := st.DB.QueryRow("SELECT \"name\" FROM \"t\" WHERE \"id\"='1'").Scan(&name); err != nil {
		t.Fatalf("查询失败: %v", err)
	}
	if name != "a1" {
		t.Fatalf("期望 name==a1，实际 %q", name)
	}
}
