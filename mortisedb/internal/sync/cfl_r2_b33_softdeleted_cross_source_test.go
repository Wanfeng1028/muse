package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestCflR2B33SoftDeletedCrossSourceConflict(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	dir := t.TempDir()

	pathA := writeCSVStr(t, dir, "a.csv", "id,name\n1,a\n2,b\n")
	srcA := config.SourceConfig{Type: "csv", Name: "A", Path: pathA, Table: "t", PrimaryKey: "id", Incremental: ""}
	pathB := writeCSVStr(t, dir, "b.csv", "")
	srcB := config.SourceConfig{Type: "csv", Name: "B", Path: pathB, Table: "t", PrimaryKey: "id", Incremental: ""}

	cfg := &config.Config{
		Sources: []config.SourceConfig{srcA, srcB},
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"A", "B"}, SoftDelete: true, BatchSize: 100},
	}

	// round1: 源 A 写入两行
	stats, err := Sync(cfg, st, []string{"A"}, "j1")
	if err != nil {
		t.Fatalf("round1 Sync 失败: %v", err)
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
		t.Fatalf("round1 未找到源 A 表 t 的统计")
	}
	if tsA.Inserted != 2 {
		t.Fatalf("round1 期望 Inserted==2，实际 %d", tsA.Inserted)
	}

	// round2: 源 A 移除 id=2 → 软删除
	pathA2 := writeCSVStr(t, dir, "a2.csv", "id,name\n1,a\n")
	srcA2 := config.SourceConfig{Type: "csv", Name: "A", Path: pathA2, Table: "t", PrimaryKey: "id", Incremental: ""}
	cfg2 := &config.Config{
		Sources: []config.SourceConfig{srcA2, srcB},
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"A", "B"}, SoftDelete: true, BatchSize: 100},
	}
	stats2, err := Sync(cfg2, st, []string{"A"}, "j1")
	if err != nil {
		t.Fatalf("round2 Sync 失败: %v", err)
	}
	var tsA2 *TableStats
	for i := range stats2 {
		if stats2[i].Source != "A" {
			continue
		}
		for j := range stats2[i].Tables {
			if stats2[i].Tables[j].Table == "t" {
				tsA2 = &stats2[i].Tables[j]
			}
		}
	}
	if tsA2 == nil {
		t.Fatalf("round2 未找到源 A 表 t 的统计")
	}
	if tsA2.Deleted != 1 {
		t.Fatalf("round2 期望源 A Deleted==1，实际 %d", tsA2.Deleted)
	}

	hash2, src2, del2, found2, err := st.GetHash(st.DB, "t", "id", "2")
	if err != nil {
		t.Fatalf("round2 GetHash 失败: %v", err)
	}
	if !found2 {
		t.Fatalf("round2 期望 id=2 仍存在")
	}
	if !del2 {
		t.Fatalf("round2 期望 id=2 deleted==true，实际 false (hash=%s src=%s)", hash2, src2)
	}
	if src2 != "A" {
		t.Fatalf("round2 期望 id=2 source==A，实际 %s", src2)
	}

	// round3: 源 B 试图改写被 A 软删除的行 → 跨源冲突挂起
	pathB3 := writeCSVStr(t, dir, "b3.csv", "id,name\n2,B2\n")
	srcB3 := config.SourceConfig{Type: "csv", Name: "B", Path: pathB3, Table: "t", PrimaryKey: "id", Incremental: ""}
	cfg3 := &config.Config{
		Sources: []config.SourceConfig{srcA2, srcB3},
		Sync:    config.SyncPolicy{Conflict: "priority", Priority: []string{"A", "B"}, SoftDelete: true, BatchSize: 100},
	}
	stats3, err := Sync(cfg3, st, []string{"B"}, "j1")
	if err != nil {
		t.Fatalf("round3 Sync 失败: %v", err)
	}
	var ts *TableStats
	for i := range stats3 {
		if stats3[i].Source != "B" {
			continue
		}
		for j := range stats3[i].Tables {
			if stats3[i].Tables[j].Table == "t" {
				ts = &stats3[i].Tables[j]
			}
		}
	}
	if ts == nil {
		t.Fatalf("未找到源 B 表 t 的统计")
	}
	if ts.Conflicts != 1 {
		t.Fatalf("round3 期望源 B Conflicts==1，实际 %d", ts.Conflicts)
	}
	if ts.Updated != 0 {
		t.Fatalf("round3 期望源 B Updated==0，实际 %d", ts.Updated)
	}

	hashAfter, srcAfter, delAfter, foundAfter, err := st.GetHash(st.DB, "t", "id", "2")
	if err != nil {
		t.Fatalf("round3 GetHash 失败: %v", err)
	}
	if !foundAfter {
		t.Fatalf("round3 期望 id=2 仍存在")
	}
	if !delAfter {
		t.Fatalf("round3 期望 id=2 deleted 仍为 true，实际 false")
	}
	if srcAfter != "A" {
		t.Fatalf("round3 期望 id=2 source 仍为 A，实际 %s", srcAfter)
	}
	if hashAfter != hash2 {
		t.Fatalf("round3 期望 id=2 hash 未被覆盖，实际 hash=%s 原 hash=%s", hashAfter, hash2)
	}

	var name string
	if err := st.DB.QueryRow("SELECT name FROM t WHERE id = ?", "2").Scan(&name); err != nil {
		t.Fatalf("查询 id=2 name 失败: %v", err)
	}
	if name != "b" {
		t.Fatalf("round3 期望 id=2 name 仍为 b（未被覆盖），实际 %s", name)
	}

	pend, err := st.ListConflicts("pending")
	if err != nil {
		t.Fatalf("ListConflicts 失败: %v", err)
	}
	if len(pend) != 1 {
		t.Fatalf("期望 pending 冲突数==1，实际 %d", len(pend))
	}
	if pend[0].SourceA != "A" {
		t.Fatalf("期望冲突 SourceA==A，实际 %s", pend[0].SourceA)
	}
	if pend[0].SourceB != "B" {
		t.Fatalf("期望冲突 SourceB==B，实际 %s", pend[0].SourceB)
	}
}
