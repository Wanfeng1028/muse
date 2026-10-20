package sync

import (
	"testing"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

func TestCflR2B32SoftDeletedReviveBySameSource(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if err := st.Migrate(); err != nil {
		t.Fatalf("迁移失败: %v", err)
	}

	// round1
	dir1 := t.TempDir()
	path1 := writeCSVStr(t, dir1, "s1.csv", "id,name\n1,a\n2,b\n")
	src := config.SourceConfig{Type: "csv", Name: "s1", Path: path1, Table: "t", PrimaryKey: "id", Incremental: ""}
	cfg := &config.Config{
		Sources: []config.SourceConfig{src},
		Sync:    config.SyncPolicy{Conflict: "update", SoftDelete: true, BatchSize: 100},
	}
	stats, err := Sync(cfg, st, []string{"s1"}, "j1")
	if err != nil {
		t.Fatalf("round1 Sync 失败: %v", err)
	}
	cnt, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("round1 TableCount 失败: %v", err)
	}
	if cnt != 2 {
		t.Fatalf("round1 TableCount = %d, 期望 2", cnt)
	}
	var ts1 *TableStats
	for i := range stats {
		for j := range stats[i].Tables {
			if stats[i].Tables[j].Table == "t" {
				ts1 = &stats[i].Tables[j]
			}
		}
	}
	if ts1 == nil {
		t.Fatalf("round1 未找到表统计 t")
	}
	if ts1.Inserted != 2 {
		t.Fatalf("round1 Inserted = %d, 期望 2", ts1.Inserted)
	}

	// round2: id=2 消失 → 软删除
	dir2 := t.TempDir()
	path2 := writeCSVStr(t, dir2, "s1.csv", "id,name\n1,a\n")
	src2 := config.SourceConfig{Type: "csv", Name: "s1", Path: path2, Table: "t", PrimaryKey: "id", Incremental: ""}
	cfg2 := &config.Config{
		Sources: []config.SourceConfig{src2},
		Sync:    config.SyncPolicy{Conflict: "update", SoftDelete: true, BatchSize: 100},
	}
	stats2, err := Sync(cfg2, st, []string{"s1"}, "j1")
	if err != nil {
		t.Fatalf("round2 Sync 失败: %v", err)
	}
	var ts2 *TableStats
	for i := range stats2 {
		for j := range stats2[i].Tables {
			if stats2[i].Tables[j].Table == "t" {
				ts2 = &stats2[i].Tables[j]
			}
		}
	}
	if ts2 == nil {
		t.Fatalf("round2 未找到表统计 t")
	}
	if ts2.Deleted != 1 {
		t.Fatalf("round2 Deleted = %d, 期望 1", ts2.Deleted)
	}
	cnt2, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("round2 TableCount 失败: %v", err)
	}
	if cnt2 != 1 {
		t.Fatalf("round2 TableCount = %d, 期望 1", cnt2)
	}
	_, _, deleted2, found2, err := st.GetHash(st.DB, "t", "id", "2")
	if err != nil {
		t.Fatalf("round2 GetHash 失败: %v", err)
	}
	if !found2 {
		t.Fatalf("round2 GetHash found = false, 期望 true")
	}
	if !deleted2 {
		t.Fatalf("round2 GetHash deleted = false, 期望 true")
	}

	// round3: id=2 以相同内容回来 → 复活
	dir3 := t.TempDir()
	path3 := writeCSVStr(t, dir3, "s1.csv", "id,name\n1,a\n2,b\n")
	src3 := config.SourceConfig{Type: "csv", Name: "s1", Path: path3, Table: "t", PrimaryKey: "id", Incremental: ""}
	cfg3 := &config.Config{
		Sources: []config.SourceConfig{src3},
		Sync:    config.SyncPolicy{Conflict: "update", SoftDelete: true, BatchSize: 100},
	}
	stats3, err := Sync(cfg3, st, []string{"s1"}, "j1")
	if err != nil {
		t.Fatalf("round3 Sync 失败: %v", err)
	}
	var ts3 *TableStats
	for i := range stats3 {
		for j := range stats3[i].Tables {
			if stats3[i].Tables[j].Table == "t" {
				ts3 = &stats3[i].Tables[j]
			}
		}
	}
	if ts3 == nil {
		t.Fatalf("round3 未找到表统计 t")
	}
	if ts3.Updated != 1 {
		t.Fatalf("round3 Updated = %d, 期望 1", ts3.Updated)
	}
	cnt3, err := st.TableCount("t")
	if err != nil {
		t.Fatalf("round3 TableCount 失败: %v", err)
	}
	if cnt3 != 2 {
		t.Fatalf("round3 TableCount = %d, 期望 2", cnt3)
	}
	_, _, deleted3, found3, err := st.GetHash(st.DB, "t", "id", "2")
	if err != nil {
		t.Fatalf("round3 GetHash 失败: %v", err)
	}
	if !found3 {
		t.Fatalf("round3 GetHash found = false, 期望 true")
	}
	if deleted3 {
		t.Fatalf("round3 GetHash deleted = true, 期望 false（复活）")
	}
	rows, err := st.DB.Query("SELECT name FROM t WHERE id = ?", 2)
	if err != nil {
		t.Fatalf("round3 查询行失败: %v", err)
	}
	defer rows.Close()
	if !rows.Next() {
		t.Fatalf("round3 未找到 id=2 的行")
	}
	var name string
	if err := rows.Scan(&name); err != nil {
		t.Fatalf("round3 扫描行失败: %v", err)
	}
	if name != "b" {
		t.Fatalf("round3 id=2 name = %q, 期望 %q", name, "b")
	}
}
